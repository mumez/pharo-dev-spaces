import json
import subprocess

from pds import mcp_config
from pds.mcp_config import (
    claude_command,
    cursor_agent_command,
    cursor_agent_cache_workspace_dir,
    cursor_mcp_config,
    launch_claude,
    launch_cursor_agent,
    resolve_cursor_agent_paths,
    slot_mcp_config,
    write_slot_cursor_mcp_config,
    write_slot_mcp_config,
)
from pds.slot import slot_dir


def test_slot_mcp_config_points_smalltalk_interop_to_slot_port(layout):
    servers = slot_mcp_config(layout, 2)["mcpServers"]

    assert servers["smalltalk-interop"]["env"]["SIS_PORT"] == "8088"
    assert "smalltalk-validator" in servers


def test_cursor_mcp_config_uses_env_interpolation_for_sis_port(layout):
    servers = cursor_mcp_config(layout)["mcpServers"]

    assert servers["smalltalk-interop"]["env"]["SIS_PORT"] == "${env:SIS_PORT}"


def test_cursor_mcp_config_merges_into_existing_servers_without_dropping_them(layout):
    existing = {
        "mcpServers": {
            "playwright": {"command": "npx", "args": ["-y", "@playwright/mcp"]},
            "smalltalk-interop": {"command": "other", "env": {"SIS_PORT": "9999"}},
        },
        "keepThisTopLevel": True,
    }

    merged = cursor_mcp_config(layout, existing=existing)

    assert merged["keepThisTopLevel"] is True
    assert merged["mcpServers"]["playwright"] == existing["mcpServers"]["playwright"]
    assert merged["mcpServers"]["smalltalk-interop"]["env"]["SIS_PORT"] == "${env:SIS_PORT}"
    assert "smalltalk-validator" in merged["mcpServers"]


def test_write_cursor_mcp_config_preserves_existing_project_servers(layout, tmp_path):
    from pds.mcp_config import write_cursor_mcp_config

    workspace = tmp_path / "Stick"
    path = workspace / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"my-server": {"command": "true"}}}) + "\n")

    write_cursor_mcp_config(layout, workspace)

    servers = json.loads(path.read_text())["mcpServers"]
    assert servers["my-server"] == {"command": "true"}
    assert servers["smalltalk-interop"]["env"]["SIS_PORT"] == "${env:SIS_PORT}"


def test_slot_mcp_config_merges_other_servers(layout):
    layout.mcp_others_file.write_text(json.dumps({"mcpServers": {"zvec_grep": {"command": "zvec"}}}))

    servers = slot_mcp_config(layout, 1)["mcpServers"]

    assert servers["zvec_grep"] == {"command": "zvec"}
    assert servers["smalltalk-interop"]["env"]["SIS_PORT"] == "8087"


def test_smalltalk_dev_servers_win_over_same_named_other_servers(layout):
    layout.mcp_others_file.write_text(json.dumps({"mcpServers": {"smalltalk-interop": {"command": "other"}}}))

    servers = slot_mcp_config(layout, 1)["mcpServers"]

    assert servers["smalltalk-interop"]["env"]["SIS_PORT"] == "8087"


def test_write_slot_mcp_config_writes_into_slot_dir(layout):
    path = write_slot_mcp_config(layout, 3)

    assert path == slot_dir(layout, 3) / "mcp.json"
    assert json.loads(path.read_text()) == slot_mcp_config(layout, 3)


def test_write_slot_cursor_mcp_config_writes_outside_the_git_tree(layout, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    path = write_slot_cursor_mcp_config(layout, 2)

    assert path == tmp_path / "cache" / "pharo-dev-spaces" / "slot2" / ".cursor" / "mcp.json"
    assert json.loads(path.read_text()) == cursor_mcp_config(layout)
    assert path != slot_dir(layout, 2) / ".cursor" / "mcp.json"


def test_claude_command_uses_only_the_slot_mcp_config(tmp_path):
    command = claude_command(tmp_path / "mcp.json", ["--model", "opus"])

    assert command == [
        "claude", "--strict-mcp-config", "--mcp-config", str(tmp_path / "mcp.json"), "--model", "opus",
    ]


def test_cursor_agent_command_uses_slot_workspace_and_approves_mcps(tmp_path):
    slot_workspace = tmp_path / "slot2"
    project = tmp_path / "project"
    slot_workspace.mkdir()
    project.mkdir()

    command = cursor_agent_command(slot_workspace, ["-p", "/st-eval Smalltalk version"], add_dir=project)

    assert command == [
        "cursor-agent",
        "--workspace",
        str(slot_workspace),
        "--approve-mcps",
        "--add-dir",
        str(project),
        "-p",
        "/st-eval Smalltalk version",
    ]


def test_cursor_agent_command_skips_add_dir_when_it_is_the_workspace(tmp_path):
    slot_workspace = tmp_path / "slot2"
    slot_workspace.mkdir()

    command = cursor_agent_command(slot_workspace, [], add_dir=slot_workspace)

    assert command == ["cursor-agent", "--workspace", str(slot_workspace), "--approve-mcps"]


def init_git_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)


def test_resolve_uses_standalone_git_root_as_workspace(layout, tmp_path):
    stick = tmp_path / "Stick"
    init_git_repo(stick)

    workspace, add_dir = resolve_cursor_agent_paths(layout, 2, project=stick)

    assert workspace == stick.resolve()
    assert add_dir is None


def test_resolve_uses_cache_when_project_is_inside_another_repo(layout, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    nested = layout.root / "nested-project"
    nested.mkdir()

    workspace, add_dir = resolve_cursor_agent_paths(layout, 2, project=nested)

    assert workspace == cursor_agent_cache_workspace_dir(2)
    assert add_dir == nested.resolve()


def test_resolve_uses_cache_for_the_pds_root_itself(layout, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    init_git_repo(layout.root)

    workspace, add_dir = resolve_cursor_agent_paths(layout, 1, project=layout.root)

    assert workspace == cursor_agent_cache_workspace_dir(1)
    assert add_dir == layout.root.resolve()


def test_launch_claude_warns_when_slot_is_not_running(layout, monkeypatch, capsys):
    executed = []
    monkeypatch.setattr(mcp_config.os, "execvp", lambda program, command: executed.append(command))

    launch_claude(layout, 1, [])

    assert "pds slot 1 up" in capsys.readouterr().err
    assert executed[0][:2] == ["claude", "--strict-mcp-config"]


def test_launch_cursor_agent_defaults_to_cache_workspace_for_cwd_inside_pds(layout, monkeypatch, capsys, tmp_path):
    executed = []
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.delenv("SIS_PORT", raising=False)
    monkeypatch.setattr(mcp_config.os, "execvp", lambda program, command: executed.append(command))
    monkeypatch.setattr(mcp_config.os, "getcwd", lambda: str(layout.root))

    launch_cursor_agent(layout, 2, ["-p", "/st-eval Smalltalk version"])

    workspace = cursor_agent_cache_workspace_dir(2)
    assert "pds slot 2 up" in capsys.readouterr().err
    assert json.loads((workspace / ".cursor" / "mcp.json").read_text()) == cursor_mcp_config(layout)
    assert mcp_config.os.environ["SIS_PORT"] == "8088"
    assert executed[0] == [
        "cursor-agent",
        "--workspace",
        str(workspace),
        "--approve-mcps",
        "--add-dir",
        str(layout.root),
        "-p",
        "/st-eval Smalltalk version",
    ]


def test_launch_cursor_agent_with_project_writes_shared_env_based_mcp(layout, monkeypatch, capsys, tmp_path):
    executed = []
    stick = tmp_path / "Stick"
    init_git_repo(stick)
    monkeypatch.delenv("SIS_PORT", raising=False)
    monkeypatch.setattr(mcp_config.os, "execvp", lambda program, command: executed.append(command))

    launch_cursor_agent(layout, 1, ["-p", "fix tests"], project=stick)
    first_config = (stick / ".cursor" / "mcp.json").read_text()
    launch_cursor_agent(layout, 2, ["-p", "fix tests"], project=stick)

    assert "pds slot 2 up" in capsys.readouterr().err
    assert first_config == (stick / ".cursor" / "mcp.json").read_text()
    assert json.loads(first_config)["mcpServers"]["smalltalk-interop"]["env"]["SIS_PORT"] == "${env:SIS_PORT}"
    assert mcp_config.os.environ["SIS_PORT"] == "8088"
    assert executed[-1][:3] == ["cursor-agent", "--workspace", str(stick.resolve())]
