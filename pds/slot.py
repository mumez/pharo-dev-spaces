"""Fixed, disposable slots (slots/slot1..5) derived from the current snapshot."""

import json
import os
import shutil
import signal
import subprocess
import time

from pds.image_dir import copy_image, image_path, staged_replacement
from pds.pharo import (
    STANDALONE_SIS_PORT,
    default_ripple_port,
    ensure_pharo_ports_available,
    keep_alive_command,
    pharo_environment,
    pharo_ui_command,
)
from pds.snapshot import latest_manifest_path

SLOT_NUMBERS = (1, 2, 3, 4, 5)
SLOT_BASE_PORT = STANDALONE_SIS_PORT  # stays free for a standalone image; slot N listens on 8086 + N
STOP_TIMEOUT_SECONDS = 10
ORIGIN_FILE_NAME = "origin.json"
PORTS_FILE_NAME = "ports.json"  # optional per-slot override: {"sis": 8089, "ripple": 9189}
# Per-slot settings that outlive the image: port overrides and AgenticBrowser settings saved by the image.
NAMES_KEPT_ACROSS_RESET = (PORTS_FILE_NAME, "agentic-browser")
PORT_OVERRIDE_KEYS = {"sis", "ripple"}


def default_slot_port(slot_number):
    if slot_number not in SLOT_NUMBERS:
        raise ValueError(f"slot number must be one of {SLOT_NUMBERS}, got {slot_number}")
    return SLOT_BASE_PORT + slot_number


def slot_ports(layout, slot_number):
    """SIS/Ripple ports: 8086 + N and SIS + 1000 unless overridden by keys in slots/slotN/ports.json."""
    ports_file = slot_dir(layout, slot_number) / PORTS_FILE_NAME
    try:
        overrides = json.loads(ports_file.read_text()) if ports_file.exists() else {}
    except json.JSONDecodeError as syntax_error:
        raise ValueError(f"{ports_file}: {syntax_error}") from syntax_error
    unknown_keys = overrides.keys() - PORT_OVERRIDE_KEYS
    if unknown_keys:
        raise ValueError(f"{ports_file}: unknown keys {sorted(unknown_keys)}; expected {sorted(PORT_OVERRIDE_KEYS)}")
    sis_port = overrides.get("sis", default_slot_port(slot_number))
    return {"sis": sis_port, "ripple": overrides.get("ripple", default_ripple_port(sis_port))}


def slot_dir(layout, slot_number):
    default_slot_port(slot_number)
    return layout.slots_dir / f"slot{slot_number}"


def pid_file(layout, slot_number):
    return slot_dir(layout, slot_number) / "pharo.pid"


def slot_origin_dir(layout):
    for origin_dir in (layout.current_snapshot_dir, layout.dev_base_dir):
        if image_path(origin_dir).exists():
            return origin_dir
    raise FileNotFoundError("neither snapshots/current nor dev-base exists; run `pds prepare-dev-base` first")


def slot_origin(layout, origin_dir):
    """Where a slot image comes from: snapshots/current with its manifest date and build time, or dev-base."""
    if origin_dir == layout.current_snapshot_dir:
        manifest_path = latest_manifest_path(layout)
        if manifest_path:
            built_at = json.loads(manifest_path.read_text()).get("builtAt")  # absent in older manifests
            return {"source": "snapshots/current", "snapshot": manifest_path.stem, "builtAt": built_at}
        return {"source": "snapshots/current", "snapshot": None, "builtAt": None}
    return {"source": "dev-base", "snapshot": None, "builtAt": None}


def read_slot_origin(layout, slot_number):
    """The origin recorded at the last reset, or None for a slot reset before origins were recorded."""
    origin_file = slot_dir(layout, slot_number) / ORIGIN_FILE_NAME
    return json.loads(origin_file.read_text()) if origin_file.exists() else None


def slot_pid(layout, slot_number):
    """Pid of the running slot, or None (a stale pid file is removed)."""
    slot_pid_file = pid_file(layout, slot_number)
    if not slot_pid_file.exists():
        return None
    pid = int(slot_pid_file.read_text())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        slot_pid_file.unlink()
        return None
    return pid


def is_slot_running(layout, slot_number):
    return slot_pid(layout, slot_number) is not None


def slot_status(layout, slot_number):
    """A slot is free for a new session when it is not running."""
    pid = slot_pid(layout, slot_number)
    status = {"slot": slot_number}
    try:
        ports = slot_ports(layout, slot_number)
        status.update(port=ports["sis"], ripplePort=ports["ripple"])
    except ValueError as ports_error:  # a broken ports.json must not hide the other slots in list-slots
        status.update(port=None, ripplePort=None, portsError=str(ports_error))
    return {
        **status,
        "hasImage": image_path(slot_dir(layout, slot_number)).exists(),
        "running": pid is not None,
        "pid": pid,
        "origin": read_slot_origin(layout, slot_number),
    }


def ensure_slot_stopped(layout, slot_number):
    if is_slot_running(layout, slot_number):
        raise RuntimeError(f"slot{slot_number} is running; run `pds slot {slot_number} down` first")


def reset_slot(layout, slot_number):
    ensure_slot_stopped(layout, slot_number)
    with staged_replacement(slot_dir(layout, slot_number), force=True) as staging_dir:
        origin_dir = slot_origin_dir(layout)
        copy_image(layout, origin_dir, staging_dir)
        (staging_dir / ORIGIN_FILE_NAME).write_text(json.dumps(slot_origin(layout, origin_dir), indent=2) + "\n")
        keep_slot_settings(slot_dir(layout, slot_number), staging_dir)


def keep_slot_settings(old_slot_dir, staging_dir):
    for name in NAMES_KEPT_ACROSS_RESET:
        kept = old_slot_dir / name
        if kept.is_dir():
            shutil.copytree(kept, staging_dir / name, symlinks=True)
        elif kept.exists():
            shutil.copy2(kept, staging_dir / name)


def start_slot(layout, slot_number, gui=False):
    """Start the slot in the background. gui=True uses pharo-ui; otherwise headless keep-alive."""
    ensure_slot_stopped(layout, slot_number)
    slot_image = image_path(slot_dir(layout, slot_number))
    if not slot_image.exists():
        raise FileNotFoundError(f"{slot_image} does not exist; run `pds slot {slot_number} reset` first")
    ports = slot_ports(layout, slot_number)
    environment = pharo_environment(ports["sis"], ports["ripple"])
    ensure_pharo_ports_available(environment)
    command = pharo_ui_command(layout, slot_image) if gui else keep_alive_command(layout, slot_image)
    with open(slot_dir(layout, slot_number) / "pharo.log", "ab") as log:
        process = subprocess.Popen(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_file(layout, slot_number).write_text(str(process.pid))


def stop_slot(layout, slot_number):
    """Terminate the slot's process group (the pharo launcher script and its VM child)."""
    pid = slot_pid(layout, slot_number)
    if pid is None:
        return
    os.killpg(pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
    while is_process_group_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    if is_process_group_alive(pid):
        os.killpg(pid, signal.SIGKILL)
    pid_file(layout, slot_number).unlink(missing_ok=True)


def is_process_group_alive(process_group_id):
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    reap_if_child(process_group_id)
    return True


def reap_if_child(pid):
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        pass
