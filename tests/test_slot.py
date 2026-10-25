import json
import os
import subprocess
import time
import urllib.request

import pytest

from pds import slot
from pds.pharo import PortInUseError
from pds.slot import (
    default_slot_port,
    is_slot_running,
    reset_slot,
    slot_dir,
    slot_origin_dir,
    slot_ports,
    slot_status,
    start_slot,
    stop_slot,
)
from tests.test_image_dir import make_image_dir


@pytest.mark.parametrize("slot_number, port", [(1, 8087), (2, 8088), (3, 8089), (4, 8090), (5, 8091)])
def test_slot_port_is_8086_plus_slot_number(slot_number, port):
    assert default_slot_port(slot_number) == port


@pytest.mark.parametrize("slot_number", [0, 6])
def test_slot_number_outside_1_to_5_is_rejected(slot_number):
    with pytest.raises(ValueError):
        default_slot_port(slot_number)


@pytest.fixture
def launches(monkeypatch):
    """(command, kwargs) of each Popen start_slot makes; the port check is skipped."""
    recorded = []

    class FakePopen:
        pid = 4242

        def __init__(self, command, **kwargs):
            recorded.append((command, kwargs))

    monkeypatch.setattr(slot.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(slot, "ensure_pharo_ports_available", lambda environment: None)
    return recorded


def write_ports_file(layout, slot_number, overrides):
    slot_dir(layout, slot_number).mkdir(parents=True, exist_ok=True)
    (slot_dir(layout, slot_number) / "ports.json").write_text(json.dumps(overrides))


def test_slot_ports_default_to_8086_plus_n_and_ripple_1000_above(layout):
    assert slot_ports(layout, 3) == {"sis": 8089, "ripple": 9089}


def test_ports_file_overrides_only_the_keys_it_contains(layout):
    write_ports_file(layout, 3, {"ripple": 9189})

    assert slot_ports(layout, 3) == {"sis": 8089, "ripple": 9189}


def test_ripple_port_follows_overridden_sis_port(layout):
    write_ports_file(layout, 2, {"sis": 8188})

    assert slot_ports(layout, 2) == {"sis": 8188, "ripple": 9188}


def test_ports_file_with_unknown_key_is_rejected(layout):
    write_ports_file(layout, 1, {"sisPort": 8187})

    with pytest.raises(ValueError, match="sisPort"):
        slot_ports(layout, 1)


def test_status_reports_broken_ports_file_instead_of_failing(layout):
    write_ports_file(layout, 1, {"sisPort": 8187})

    status = slot_status(layout, 1)

    assert status["port"] is None
    assert status["ripplePort"] is None
    assert "sisPort" in status["portsError"]


def test_ports_file_with_syntax_error_names_the_file(layout):
    slot_dir(layout, 2).mkdir(parents=True)
    (slot_dir(layout, 2) / "ports.json").write_text('{"sis": ')

    with pytest.raises(ValueError, match="slot2/ports.json"):
        slot_ports(layout, 2)


def test_reset_slot_keeps_ports_file(layout):
    make_image_dir(layout.plain_dir)
    make_image_dir(layout.dev_base_dir)
    write_ports_file(layout, 3, {"ripple": 9189})

    reset_slot(layout, 3)

    assert slot_ports(layout, 3) == {"sis": 8089, "ripple": 9189}


def test_reset_slot_keeps_agentic_browser_settings(layout):
    make_image_dir(layout.plain_dir)
    make_image_dir(layout.dev_base_dir)
    settings_file = slot_dir(layout, 1) / "agentic-browser" / "nested" / "settings.json"
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text('{"model": "custom"}')

    reset_slot(layout, 1)

    assert settings_file.read_text() == '{"model": "custom"}'
    assert (slot_dir(layout, 1) / "Pharo.image").read_text() == "image"


def test_slot_origin_prefers_current_snapshot(layout):
    make_image_dir(layout.dev_base_dir)
    make_image_dir(layout.current_snapshot_dir)

    assert slot_origin_dir(layout) == layout.current_snapshot_dir


def test_slot_origin_falls_back_to_dev_base(layout):
    make_image_dir(layout.dev_base_dir)

    assert slot_origin_dir(layout) == layout.dev_base_dir


def test_slot_origin_requires_dev_base_or_snapshot(layout):
    with pytest.raises(FileNotFoundError):
        slot_origin_dir(layout)


def test_reset_slot_recreates_slot_from_origin(layout):
    make_image_dir(layout.plain_dir)
    make_image_dir(layout.dev_base_dir)
    make_image_dir(slot_dir(layout, 2))
    (slot_dir(layout, 2) / "Pharo.image").write_text("dirty")

    reset_slot(layout, 2)

    assert (slot_dir(layout, 2) / "Pharo.image").read_text() == "image"
    assert not (slot_dir(layout, 2) / "pharo-local").exists()


def test_status_reports_dev_base_origin_after_reset(layout):
    make_image_dir(layout.plain_dir)
    make_image_dir(layout.dev_base_dir)

    reset_slot(layout, 1)

    assert slot_status(layout, 1)["origin"] == {"source": "dev-base", "snapshot": None, "builtAt": None}


def test_status_reports_snapshot_date_after_reset_from_current_snapshot(layout):
    make_image_dir(layout.plain_dir)
    make_image_dir(layout.current_snapshot_dir)
    (layout.snapshots_dir / "2026-10-12.json").write_text("{}")
    (layout.snapshots_dir / "2026-10-15.json").write_text(json.dumps({"builtAt": "2026-10-15T09:30:15"}))

    reset_slot(layout, 2)
    (layout.snapshots_dir / "2026-10-16.json").write_text("{}")

    assert slot_status(layout, 2)["origin"] == {
        "source": "snapshots/current",
        "snapshot": "2026-10-15",
        "builtAt": "2026-10-15T09:30:15",
    }


def test_status_reports_no_build_time_for_manifest_written_before_build_times_were_recorded(layout):
    make_image_dir(layout.plain_dir)
    make_image_dir(layout.current_snapshot_dir)
    (layout.snapshots_dir / "2026-10-12.json").write_text("{}")

    reset_slot(layout, 1)

    assert slot_status(layout, 1)["origin"]["builtAt"] is None


def write_pid(layout, slot_number, pid):
    slot_dir(layout, slot_number).mkdir(parents=True, exist_ok=True)
    (slot_dir(layout, slot_number) / "pharo.pid").write_text(str(pid))


def test_slot_with_live_pid_is_running(layout):
    write_pid(layout, 1, os.getpid())

    assert is_slot_running(layout, 1)


def test_status_of_running_slot_reports_pid_and_port(layout):
    make_image_dir(slot_dir(layout, 2))
    write_pid(layout, 2, os.getpid())

    assert slot_status(layout, 2) == {
        "slot": 2,
        "port": 8088,
        "ripplePort": 9088,
        "hasImage": True,
        "running": True,
        "pid": os.getpid(),
        "origin": None,
    }


def test_status_of_slot_never_reset_is_free_without_image(layout):
    assert slot_status(layout, 3) == {
        "slot": 3,
        "port": 8089,
        "ripplePort": 9089,
        "hasImage": False,
        "running": False,
        "pid": None,
        "origin": None,
    }


def test_slot_with_stale_pid_is_not_running(layout):
    finished = subprocess.Popen(["true"])
    finished.wait()
    write_pid(layout, 1, finished.pid)

    assert not is_slot_running(layout, 1)
    assert not (slot_dir(layout, 1) / "pharo.pid").exists()


def test_running_slot_cannot_be_reset_or_started(layout):
    write_pid(layout, 1, os.getpid())

    with pytest.raises(RuntimeError, match="running"):
        reset_slot(layout, 1)
    with pytest.raises(RuntimeError, match="running"):
        start_slot(layout, 1)


def test_start_slot_requires_reset_first(layout):
    with pytest.raises(FileNotFoundError, match="slot 1 reset"):
        start_slot(layout, 1)


def test_start_slot_refuses_when_slot_ports_are_in_use(layout, monkeypatch):
    make_image_dir(slot_dir(layout, 3))
    checked_ports = []

    def port_in_use(environment):
        checked_ports.append(environment["PHARO_RIPPLE_PORT"])
        raise PortInUseError("Ripple port 9089 is already in use")

    monkeypatch.setattr(slot, "ensure_pharo_ports_available", port_in_use)

    with pytest.raises(PortInUseError):
        start_slot(layout, 3)
    assert checked_ports == ["9089"]
    assert not (slot_dir(layout, 3) / "pharo.pid").exists()


def test_start_slot_launches_headless_image_on_slot_port(layout, launches):
    make_image_dir(slot_dir(layout, 3))

    start_slot(layout, 3)

    command, kwargs = launches[0]
    assert command[0].endswith("pharo")
    assert command[1] == str(slot_dir(layout, 3) / "Pharo.image")
    assert command[2:] == ["eval", "--no-quit", "nil"]
    assert kwargs["env"]["PHARO_SIS_PORT"] == "8089"
    assert kwargs["start_new_session"] is True
    assert (slot_dir(layout, 3) / "pharo.pid").read_text() == "4242"


def test_start_slot_uses_ports_file(layout, launches):
    make_image_dir(slot_dir(layout, 3))
    write_ports_file(layout, 3, {"ripple": 9189})

    start_slot(layout, 3)

    _, kwargs = launches[0]
    assert kwargs["env"]["PHARO_SIS_PORT"] == "8089"
    assert kwargs["env"]["PHARO_RIPPLE_PORT"] == "9189"


def test_start_slot_gui_launches_pharo_ui_on_slot_port(layout, launches):
    make_image_dir(slot_dir(layout, 2))

    start_slot(layout, 2, gui=True)

    command, kwargs = launches[0]
    assert command == [str(layout.plain_dir / "pharo-ui"), str(slot_dir(layout, 2) / "Pharo.image")]
    assert kwargs["env"]["PHARO_SIS_PORT"] == "8088"
    assert (slot_dir(layout, 2) / "pharo.pid").read_text() == "4242"


def test_stop_slot_terminates_the_whole_process_group(layout):
    sleeper = subprocess.Popen(["bash", "-c", "sleep 60 & wait"], start_new_session=True)
    write_pid(layout, 1, sleeper.pid)

    stop_slot(layout, 1)

    assert sleeper.wait(timeout=5) is not None
    assert not is_slot_running(layout, 1)


def sis_eval(port, code):
    request = urllib.request.Request(
        f"http://localhost:{port}/eval",
        data=json.dumps({"code": code}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)["result"]


def wait_for_sis(port, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return sis_eval(port, "1")
        except OSError:
            time.sleep(0.5)
    raise TimeoutError(f"SIS did not answer on {port}")


@pytest.mark.pharo
def test_slots_run_concurrently_and_independently(dev_base_layout):
    for slot_number in (1, 2):
        reset_slot(dev_base_layout, slot_number)
        start_slot(dev_base_layout, slot_number)
    try:
        wait_for_sis(8087)
        wait_for_sis(8088)

        sis_eval(8087, "Smalltalk at: #PdsSlotMarker put: 1")

        assert sis_eval(8087, "Smalltalk includesKey: #PdsSlotMarker") is True
        assert sis_eval(8088, "Smalltalk includesKey: #PdsSlotMarker") is False
        assert "printStringLimited" in sis_eval(8088, "(Object >> #printString) sourceCode")
    finally:
        for slot_number in (1, 2):
            stop_slot(dev_base_layout, slot_number)
