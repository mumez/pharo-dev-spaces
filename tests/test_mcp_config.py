import json

import pytest

from pds import mcp_config
from pds.mcp_config import (
    agent_workdir,
    cursor_agent_command,
    cursor_mcp_config,
    installed_smalltalk_dev_plugin_follows_sis_port,
    launch_claude,
    launch_cursor_agent,
    write_cursor_mcp_config,
)


def test_cursor_mcp_config_uses_env_interpolation_for_sis_port():
    servers = cursor_mcp_config()["mcpServers"]

    assert servers["smalltalk-interop"]["env"]["SIS_PORT"] == "${env:SIS_PORT}"
    assert "smalltalk-validator" in servers


def test_cursor_mcp_config_merges_into_existing_servers_without_dropping_them():
    existing = {
        "mcpServers": {
            "playwright": {"command": "npx", "args": ["-y", "@playwright/mcp"]},
            "smalltalk-interop": {"command": "other", "env": {"SIS_PORT": "9999"}},
        },
        "keepThisTopLevel": True,
    }

    merged = cursor_mcp_config(existing=existing)

    assert merged["keepThisTopLevel"] is True
    assert merged["mcpServers"]["playwright"] == existing["mcpServers"]["playwright"]
    assert merged["mcpServers"]["smalltalk-interop"]["env"]["SIS_PORT"] == "${env:SIS_PORT}"
    assert "smalltalk-validator" in merged["mcpServers"]


def test_write_cursor_mcp_config_preserves_existing_project_servers_and_warns(tmp_path, capsys):
    workdir = tmp_path / "Stick"
    path = workdir / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"my-server": {"command": "true"}}}) + "\n")

    write_cursor_mcp_config(workdir)

    servers = json.loads(path.read_text())["mcpServers"]
    assert servers["my-server"] == {"command": "true"}
    assert servers["smalltalk-interop"]["env"]["SIS_PORT"] == "${env:SIS_PORT}"
    assert "Cursor does not support" in capsys.readouterr().err


def test_write_cursor_mcp_config_does_not_warn_when_unchanged(tmp_path, capsys):
    workdir = tmp_path / "Stick"
    write_cursor_mcp_config(workdir)
    capsys.readouterr()

    write_cursor_mcp_config(workdir)

    assert capsys.readouterr().err == ""


def test_cursor_agent_command_omits_approve_mcps_by_default(tmp_path):
    workdir = tmp_path / "Stick"
    workdir.mkdir()

    command = cursor_agent_command(workdir, ["-p", "/st-eval Smalltalk version"])

    assert command == [
        "cursor-agent",
        "--workspace",
        str(workdir),
        "-p",
        "/st-eval Smalltalk version",
    ]


def test_cursor_agent_command_can_opt_in_to_approve_mcps(tmp_path):
    workdir = tmp_path / "Stick"
    workdir.mkdir()

    command = cursor_agent_command(workdir, ["-p", "hi"], approve_mcps=True)

    assert command == ["cursor-agent", "--workspace", str(workdir), "--approve-mcps", "-p", "hi"]


def test_agent_workdir_defaults_to_cwd(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_config.os, "getcwd", lambda: str(tmp_path))

    assert agent_workdir() == tmp_path.resolve()


def test_agent_workdir_rejects_missing_directory(tmp_path):
    with pytest.raises(FileNotFoundError, match="workdir does not exist"):
        agent_workdir(tmp_path / "missing")


def install_smalltalk_dev_plugin(claude_config_dir, mcp_json_text):
    install_path = claude_config_dir / "plugins" / "cache" / "smalltalk-dev"
    install_path.mkdir(parents=True)
    (install_path / ".mcp.json").write_text(mcp_json_text)
    (claude_config_dir / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"plugins": {"smalltalk-dev@smalltalk-dev-marketplace": [{"installPath": str(install_path)}]}})
    )


@pytest.fixture
def claude_config_dir(monkeypatch, tmp_path):
    config_dir = tmp_path / "claude-config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    return config_dir


def test_installed_smalltalk_dev_plugin_follows_sis_port(claude_config_dir):
    install_smalltalk_dev_plugin(claude_config_dir, '{"env": {"SIS_PORT": "${SIS_PORT:-8086}"}}')

    assert installed_smalltalk_dev_plugin_follows_sis_port()


def test_installed_smalltalk_dev_plugin_with_fixed_port_does_not_follow_sis_port(claude_config_dir):
    install_smalltalk_dev_plugin(claude_config_dir, '{"env": {"SIS_PORT": "8086"}}')

    assert not installed_smalltalk_dev_plugin_follows_sis_port()


def test_missing_smalltalk_dev_plugin_does_not_follow_sis_port(claude_config_dir):
    assert not installed_smalltalk_dev_plugin_follows_sis_port()


def test_launch_claude_warns_when_slot_is_not_running(layout, monkeypatch, capsys, claude_config_dir):
    install_smalltalk_dev_plugin(claude_config_dir, '{"env": {"SIS_PORT": "${SIS_PORT:-8086}"}}')
    monkeypatch.setattr(mcp_config.os, "execvp", lambda program, command: None)
    monkeypatch.setattr(mcp_config.os, "chdir", lambda path: None)

    launch_claude(layout, 1, [])

    err = capsys.readouterr().err
    assert "pds slot 1 up" in err
    assert "smalltalk-dev plugin" not in err


def test_launch_claude_warns_when_plugin_has_fixed_port(layout, monkeypatch, capsys, claude_config_dir):
    install_smalltalk_dev_plugin(claude_config_dir, '{"env": {"SIS_PORT": "8086"}}')
    monkeypatch.setattr(mcp_config.os, "execvp", lambda program, command: None)
    monkeypatch.setattr(mcp_config.os, "chdir", lambda path: None)

    launch_claude(layout, 1, [])

    assert "smalltalk-dev plugin does not read SIS_PORT" in capsys.readouterr().err


def test_launch_claude_defaults_workdir_to_cwd(layout, monkeypatch, tmp_path, claude_config_dir):
    changed_dirs = []
    monkeypatch.setattr(mcp_config.os, "execvp", lambda program, command: None)
    monkeypatch.setattr(mcp_config.os, "chdir", changed_dirs.append)
    monkeypatch.setattr(mcp_config.os, "getcwd", lambda: str(tmp_path))

    launch_claude(layout, 1, [])

    assert changed_dirs == [tmp_path.resolve()]


def test_launch_claude_runs_plain_claude_in_workdir_with_slot_sis_port(
    layout, monkeypatch, tmp_path, claude_config_dir
):
    executed = []
    changed_dirs = []
    stick = tmp_path / "Stick"
    stick.mkdir()
    monkeypatch.delenv("SIS_PORT", raising=False)
    monkeypatch.setattr(mcp_config.os, "execvp", lambda program, command: executed.append(command))
    monkeypatch.setattr(mcp_config.os, "chdir", changed_dirs.append)

    launch_claude(layout, 2, ["-p", "fix Stick"], workdir=stick)

    assert changed_dirs == [stick.resolve()]
    assert executed == [["claude", "-p", "fix Stick"]]
    assert mcp_config.os.environ["SIS_PORT"] == "8088"
    assert not (layout.slots_dir / "slot2" / "mcp.json").exists()


def test_launch_cursor_agent_defaults_workdir_to_cwd(layout, monkeypatch, capsys, tmp_path):
    executed = []
    workdir = tmp_path / "cwd-project"
    workdir.mkdir()
    monkeypatch.delenv("SIS_PORT", raising=False)
    monkeypatch.setattr(mcp_config.os, "execvp", lambda program, command: executed.append(command))
    monkeypatch.setattr(mcp_config.os, "getcwd", lambda: str(workdir))

    launch_cursor_agent(layout, 2, ["-p", "/st-eval Smalltalk version"])

    err = capsys.readouterr().err
    assert "pds slot 2 up" in err
    assert "Cursor does not support" in err
    assert json.loads((workdir / ".cursor" / "mcp.json").read_text()) == cursor_mcp_config()
    assert mcp_config.os.environ["SIS_PORT"] == "8088"
    assert executed[0] == [
        "cursor-agent",
        "--workspace",
        str(workdir.resolve()),
        "-p",
        "/st-eval Smalltalk version",
    ]


def test_launch_cursor_agent_with_workdir_sets_sis_port_for_each_slot(layout, monkeypatch, capsys, tmp_path):
    executed = []
    stick = tmp_path / "Stick"
    stick.mkdir()
    monkeypatch.delenv("SIS_PORT", raising=False)
    monkeypatch.setattr(mcp_config.os, "execvp", lambda program, command: executed.append(command))

    launch_cursor_agent(layout, 1, ["-p", "fix tests"], workdir=stick)
    first_config = (stick / ".cursor" / "mcp.json").read_text()
    assert mcp_config.os.environ["SIS_PORT"] == "8087"

    launch_cursor_agent(layout, 2, ["-p", "fix tests"], workdir=stick, approve_mcps=True)

    assert first_config == (stick / ".cursor" / "mcp.json").read_text()
    assert json.loads(first_config)["mcpServers"]["smalltalk-interop"]["env"]["SIS_PORT"] == "${env:SIS_PORT}"
    assert mcp_config.os.environ["SIS_PORT"] == "8088"
    assert executed[-1] == [
        "cursor-agent",
        "--workspace",
        str(stick.resolve()),
        "--approve-mcps",
        "-p",
        "fix tests",
    ]
