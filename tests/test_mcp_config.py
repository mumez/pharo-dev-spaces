import json

from pds import mcp_config
from pds.mcp_config import claude_command, launch_claude, slot_mcp_config, write_slot_mcp_config
from pds.slot import slot_dir


def test_slot_mcp_config_points_smalltalk_interop_to_slot_port(layout):
    servers = slot_mcp_config(layout, 2)["mcpServers"]

    assert servers["smalltalk-interop"]["env"]["SIS_PORT"] == "8088"
    assert "smalltalk-validator" in servers


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


def test_claude_command_uses_only_the_slot_mcp_config(tmp_path):
    command = claude_command(tmp_path / "mcp.json", ["--model", "opus"])

    assert command == [
        "claude", "--strict-mcp-config", "--mcp-config", str(tmp_path / "mcp.json"), "--model", "opus",
    ]


def test_launch_claude_warns_when_slot_is_not_running(layout, monkeypatch, capsys):
    executed = []
    monkeypatch.setattr(mcp_config.os, "execvp", lambda program, command: executed.append(command))

    launch_claude(layout, 1, [])

    assert "pds slot up 1" in capsys.readouterr().err
    assert executed[0][:2] == ["claude", "--strict-mcp-config"]
