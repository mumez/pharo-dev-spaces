import json
import os
import subprocess
import time
import urllib.request

import pytest

from pds import slot
from pds.slot import (
    is_slot_running,
    reset_slot,
    slot_dir,
    slot_origin_dir,
    slot_port,
    start_slot,
    stop_slot,
)
from tests.test_image_dir import make_image_dir


@pytest.mark.parametrize("slot_number, port", [(1, 8087), (2, 8088), (3, 8089)])
def test_slot_port_is_8086_plus_slot_number(slot_number, port):
    assert slot_port(slot_number) == port


@pytest.mark.parametrize("slot_number", [0, 4])
def test_slot_number_outside_1_to_3_is_rejected(slot_number):
    with pytest.raises(ValueError):
        slot_port(slot_number)


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


def write_pid(layout, slot_number, pid):
    slot_dir(layout, slot_number).mkdir(parents=True, exist_ok=True)
    (slot_dir(layout, slot_number) / "pharo.pid").write_text(str(pid))


def test_slot_with_live_pid_is_running(layout):
    write_pid(layout, 1, os.getpid())

    assert is_slot_running(layout, 1)


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
    with pytest.raises(FileNotFoundError, match="slot reset"):
        start_slot(layout, 1)


def test_start_slot_launches_headless_image_on_slot_port(layout, monkeypatch):
    make_image_dir(slot_dir(layout, 3))
    launches = []

    class FakePopen:
        pid = 4242

        def __init__(self, command, **kwargs):
            launches.append((command, kwargs))

    monkeypatch.setattr(slot.subprocess, "Popen", FakePopen)

    start_slot(layout, 3)

    command, kwargs = launches[0]
    assert command[1] == str(slot_dir(layout, 3) / "Pharo.image")
    assert command[2:] == ["eval", "--no-quit", "nil"]
    assert kwargs["env"]["PHARO_SIS_PORT"] == "8089"
    assert kwargs["start_new_session"] is True
    assert (slot_dir(layout, 3) / "pharo.pid").read_text() == "4242"


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
