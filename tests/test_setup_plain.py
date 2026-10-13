import subprocess

import pytest

from pds.setup_plain import setup_plain


def test_setup_plain_downloads_requested_version_into_plain_dir(layout, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    setup_plain(layout, version="140")

    command, kwargs = calls[0]
    assert "https://get.pharo.org/64/140+vm" in command[-1]
    assert kwargs["cwd"] == layout.plain_dir
    assert kwargs["check"] is True
    assert layout.plain_dir.is_dir()


def test_setup_plain_refuses_to_overwrite_existing_plain_dir(layout):
    layout.plain_dir.mkdir()

    with pytest.raises(FileExistsError):
        setup_plain(layout, version="140")


def test_setup_plain_replaces_existing_plain_dir_when_forced(layout, monkeypatch):
    layout.plain_dir.mkdir()
    (layout.plain_dir / "old.image").write_text("old")
    monkeypatch.setattr(subprocess, "run", lambda command, **kw: subprocess.CompletedProcess(command, 0))

    setup_plain(layout, version="140", force=True)

    assert not (layout.plain_dir / "old.image").exists()
