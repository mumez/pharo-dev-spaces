import json
import subprocess

import pytest

from pds import pharo
from pds.pharo import PharoRunError, launch_pharo_ui, pharo_environment, pharo_ui_command, run_pharo, script_command


def test_pharo_command_runs_script_headless_and_quits(layout, tmp_path):
    image = tmp_path / "x" / "Pharo.image"
    script = tmp_path / "s.st"

    command = script_command(layout, image, script)

    assert command == [str(layout.plain_dir / "pharo"), str(image), "st", "--quit", str(script)]


def test_pharo_command_saves_when_requested(layout, tmp_path):
    command = script_command(layout, tmp_path / "Pharo.image", tmp_path / "s.st", save=True)

    assert command[2:5] == ["st", "--save", "--quit"]


def test_pharo_command_leaves_save_and_quit_to_script_when_save_is_none(layout, tmp_path):
    command = script_command(layout, tmp_path / "Pharo.image", tmp_path / "s.st", save=None)

    assert command[2:] == ["st", str(tmp_path / "s.st")]


def test_pharo_ui_command_uses_gui_launcher(layout, tmp_path):
    image = tmp_path / "Pharo.image"

    command = pharo_ui_command(layout, image)

    assert command == [str(layout.plain_dir / "pharo-ui"), str(image)]


def test_launch_pharo_ui_execs_with_sis_port(layout, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pharo.os, "execvpe", lambda path, args, env: calls.append((path, args, env)))

    launch_pharo_ui(layout, tmp_path / "Pharo.image", 8086)

    path, args, env = calls[0]
    assert path.endswith("pharo-ui")
    assert args == [str(layout.plain_dir / "pharo-ui"), str(tmp_path / "Pharo.image")]
    assert env["PHARO_SIS_PORT"] == "8086"


def test_run_pharo_passes_sis_port_and_timeout(layout, tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_pharo(layout, tmp_path / "Pharo.image", tmp_path / "s.st", port=8090, timeout=30)

    assert calls[0]["env"]["PHARO_SIS_PORT"] == "8090"
    assert calls[0]["timeout"] == 30


def test_ripple_port_follows_sis_port_and_overrides_the_shell(monkeypatch):
    monkeypatch.setenv("PHARO_RIPPLE_PORT", "8888")

    assert pharo_environment(8087)["PHARO_RIPPLE_PORT"] == "9087"


def test_run_pharo_raises_on_nonzero_exit(layout, tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda command, **kw: subprocess.CompletedProcess(command, 1))

    with pytest.raises(PharoRunError, match="exit code 1"):
        run_pharo(layout, tmp_path / "Pharo.image", tmp_path / "s.st", port=8090, timeout=30)


def test_run_pharo_raises_on_timeout(layout, tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(PharoRunError, match="timed out"):
        run_pharo(layout, tmp_path / "Pharo.image", tmp_path / "s.st", port=8090, timeout=30)


@pytest.mark.pharo
def test_run_pharo_executes_script_in_real_image(pharo_layout, tmp_path):
    image_dir = tmp_path / "image"
    image_dir.mkdir()
    for name in ("Pharo.image", "Pharo.changes"):
        (image_dir / name).write_bytes((pharo_layout.plain_dir / name).read_bytes())
    result_file = tmp_path / "result.json"
    script = tmp_path / "probe.st"
    script.write_text(
        f"'{result_file}' asFileReference writeStreamDo: [ :s | s nextPutAll: "
        '\'{"answer": \', (1 + 1) printString, \', "port": "\', '
        "(OSEnvironment current at: 'PHARO_SIS_PORT'), '\"}' ]."
    )

    run_pharo(pharo_layout, image_dir / "Pharo.image", script, port=8123, timeout=120)

    assert json.loads(result_file.read_text()) == {"answer": 2, "port": "8123"}
