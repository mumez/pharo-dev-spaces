"""Fixed, disposable slots (slots/slot1..5) derived from the current snapshot."""

import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from pds.image_dir import copy_image, image_path, staged_replacement
from pds.pharo import (
    STANDALONE_SIS_PORT,
    default_ripple_port,
    ensure_pharo_ports_available,
    keep_alive_command,
    pharo_environment,
    pharo_ui_command,
)
from pds.projects import read_projects
from pds.snapshot import latest_manifest_path

SLOT_NUMBERS = (1, 2, 3, 4, 5)
SLOT_BASE_PORT = STANDALONE_SIS_PORT  # stays free for a standalone image; slot N listens on 8086 + N
STOP_TIMEOUT_SECONDS = 10
ORIGIN_FILE_NAME = "origin.json"
PORTS_FILE_NAME = "ports.json"  # optional per-slot override: {"sis": 8089, "ripple": 9189}
REFS_FILE_NAME = "refs.json"  # branches the next `reset --load` overlays: [{"repository", "ref"}]
TESTS_FILE_NAME = "tests.json"  # last overlay test result; not kept across reset
# Per-slot settings that outlive the image: port overrides and AgenticBrowser settings saved by the image.
NAMES_KEPT_ACROSS_RESET = (PORTS_FILE_NAME, "agentic-browser")
PORT_OVERRIDE_KEYS = {"sis", "ripple"}


REF_ENTRY_KEYS = {"repository", "ref"}


def strip_origin_prefix(ref):
    prefix = "origin/"
    return ref[len(prefix) :] if ref.startswith(prefix) else ref


def parse_ref_spec(spec):
    """`NAME:BRANCH`. A leading `origin/` on the branch is the same branch without it."""
    name, separator, branch = spec.partition(":")
    branch = strip_origin_prefix(branch)
    if separator != ":" or not name or not branch:
        raise ValueError(f"--ref must be NAME:BRANCH, got {spec!r}")
    return name, branch


def resolve_project(projects, name):
    """First unique match: baseline, then repository directory name, then absolute path."""
    for label, key in (
        ("baseline", lambda project: project["baseline"]),
        ("repository directory", lambda project: Path(project["repository"]).name),
        ("repository path", lambda project: project["repository"]),
    ):
        matches = [project for project in projects if key(project) == name]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"{name} matches more than one {label} in st-projects.json")
    raise ValueError(f"{name} matches no project in st-projects.json")


def resolve_ref_specs(projects, specs):
    resolved = []
    seen = set()
    for spec in specs:
        name, branch = parse_ref_spec(spec)
        repository = resolve_project(projects, name)["repository"]
        if repository in seen:
            raise ValueError(f"{repository} is given twice")
        seen.add(repository)
        resolved.append({"repository": repository, "ref": branch})
    return resolved


def validate_saved_refs(entries, projects, source):
    """Saved refs are `{repository, ref}` only, and each repository is in st-projects.json."""
    if not isinstance(entries, list):
        raise ValueError(f"{source}: expected a list of repository refs")
    known = {project["repository"] for project in projects}
    seen = set()
    validated = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != REF_ENTRY_KEYS:
            raise ValueError(f"{source}: each ref must have only 'repository' and 'ref'")
        repository, ref = entry["repository"], entry["ref"]
        if not isinstance(repository, str) or not isinstance(ref, str):
            raise ValueError(f"{source}: repository and ref must be strings")
        ref = strip_origin_prefix(ref)
        if not ref:
            raise ValueError(f"{source}: ref must be a branch name")
        if repository not in known:
            raise ValueError(f"{source}: {repository} is not in st-projects.json")
        if repository in seen:
            raise ValueError(f"{repository} is given twice")
        seen.add(repository)
        validated.append({"repository": repository, "ref": ref})
    return validated


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
    return read_slot_json(slot_dir(layout, slot_number) / ORIGIN_FILE_NAME)


def read_saved_refs(layout, slot_number):
    """Branches saved for `reset --load`, or [] when the slot has no refs.json."""
    return read_slot_json(slot_dir(layout, slot_number) / REFS_FILE_NAME) or []


def read_slot_tests(layout, slot_number):
    """The last overlay test result, or None when this image was not tested."""
    return read_slot_json(slot_dir(layout, slot_number) / TESTS_FILE_NAME)


def read_slot_json(path):
    return json.loads(path.read_text()) if path.exists() else None


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
        "savedRefs": read_saved_refs(layout, slot_number),
        "tests": read_slot_tests(layout, slot_number),
    }


def ensure_slot_stopped(layout, slot_number):
    if is_slot_running(layout, slot_number):
        raise RuntimeError(f"slot{slot_number} is running; run `pds slot {slot_number} down` first")


def saved_refs_path(layout, slot_number):
    return slot_dir(layout, slot_number) / REFS_FILE_NAME


def load_saved_ref_request(layout, slot_number):
    refs_path = saved_refs_path(layout, slot_number)
    if not refs_path.exists():
        raise ValueError(f"{refs_path} does not exist; pass --ref NAME:BRANCH")
    try:
        entries = json.loads(refs_path.read_text())
    except json.JSONDecodeError as syntax_error:
        raise ValueError(f"{refs_path}: {syntax_error}") from syntax_error
    return validate_saved_refs(entries, read_projects(layout), refs_path)


def reset_slot(layout, slot_number, *, ref_specs=(), load_saved=False, run_tests=None, clear_refs=False):
    ensure_slot_stopped(layout, slot_number)
    overlaying = bool(ref_specs) or load_saved
    if clear_refs and overlaying:
        raise ValueError("--clear-refs cannot be combined with --ref or --load")
    if run_tests is True and not overlaying:
        raise ValueError("--test requires --ref or --load")
    if ref_specs:
        resolve_ref_specs(read_projects(layout), ref_specs)
    elif load_saved:
        load_saved_ref_request(layout, slot_number)
    if overlaying:
        raise NotImplementedError("slot overlay")
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
