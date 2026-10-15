"""Per-slot MCP configuration for Claude Code and Cursor Agent.

Claude: `claude --strict-mcp-config --mcp-config slots/slotN/mcp.json` with a
concrete SIS_PORT so the smalltalk-dev plugin's servers (fixed to 8086) are hidden.

Cursor: has no --mcp-config flag. It loads `<workspace>/.cursor/mcp.json`.
`pds slot N cursor-agent [--workspace DIR]` uses DIR (default: cwd) as
`cursor-agent --workspace`, merges smalltalk servers into that directory's
`.cursor/mcp.json` with `"SIS_PORT": "${env:SIS_PORT}"`, and sets
`SIS_PORT=8086+N` in the process environment. Cursor does not support
`${env:NAME:-default}`, so opening the project outside pds may leave an unset
SIS_PORT; pds warns when it changes the file.
"""

import json
import os
import sys
from pathlib import Path

from pds.slot import is_slot_running, slot_dir, slot_port


def _smalltalk_dev_servers(sis_port_value):
    """smalltalk-dev MCP servers; `sis_port_value` is a port string or `${env:SIS_PORT}`."""
    return {
        "smalltalk-interop": {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/mumez/smalltalk-interop-mcp-server.git",
                "smalltalk-interop-mcp-server",
            ],
            "env": {"SIS_PORT": sis_port_value},
        },
        "smalltalk-validator": {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/mumez/smalltalk-validator-mcp-server.git@main",
                "smalltalk-validator-mcp-server",
            ],
        },
    }


def smalltalk_dev_servers(sis_port):
    """Claude / concrete-port form of the smalltalk-dev servers."""
    return _smalltalk_dev_servers(str(sis_port))


def cursor_smalltalk_dev_servers():
    """Cursor form: port from process env via Cursor's `${env:NAME}` expansion."""
    return _smalltalk_dev_servers("${env:SIS_PORT}")


def other_servers(layout):
    if not layout.mcp_others_file.exists():
        return {}
    return json.loads(layout.mcp_others_file.read_text()).get("mcpServers", {})


def _merged_servers(layout, base_servers, dev_servers):
    """Merge MCP servers: base, then mcp_others.json, then smalltalk-dev (last wins)."""
    return {**base_servers, **other_servers(layout), **dev_servers}


def slot_mcp_config(layout, slot_number):
    """Claude: concrete SIS_PORT for slots/slotN/mcp.json."""
    return {"mcpServers": _merged_servers(layout, {}, smalltalk_dev_servers(slot_port(slot_number)))}


def cursor_mcp_config(layout, existing=None):
    """Cursor MCP config: merge pds servers into any existing `.cursor/mcp.json`.

    Existing servers are kept as the base. Then `mcp_others.json`, then
    smalltalk-dev — so both mcp_others and smalltalk-dev override same-named
    project servers. SIS_PORT is `${env:SIS_PORT}` (no `:-default` in Cursor).
    """
    existing = existing or {}
    existing_servers = existing.get("mcpServers", {})
    return {
        **existing,
        "mcpServers": _merged_servers(layout, existing_servers, cursor_smalltalk_dev_servers()),
    }


def _read_mcp_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _write_mcp_json(path, config):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n")
    return path


def write_slot_mcp_config(layout, slot_number):
    """Claude Code: slots/slotN/mcp.json for --mcp-config."""
    return _write_mcp_json(slot_dir(layout, slot_number) / "mcp.json", slot_mcp_config(layout, slot_number))


def cursor_workspace_dir(workspace=None):
    """Directory used as cursor-agent --workspace (`--workspace`, or cwd)."""
    workspace_dir = Path(workspace or os.getcwd()).resolve()
    if not workspace_dir.is_dir():
        raise FileNotFoundError(f"workspace directory does not exist: {workspace_dir}")
    return workspace_dir


def write_cursor_mcp_config(layout, workspace_dir):
    """Merge pds MCP servers into workspace_dir/.cursor/mcp.json (create if missing)."""
    path = Path(workspace_dir) / ".cursor" / "mcp.json"
    before = path.read_text() if path.exists() else None
    config = cursor_mcp_config(layout, existing=_read_mcp_json(path))
    written = _write_mcp_json(path, config)
    after = written.read_text()
    if before != after:
        print(
            f"pds: warning: merged smalltalk MCP servers into {path} "
            f"(SIS_PORT=${{env:SIS_PORT}}); outside pds set SIS_PORT or expect port 8086. "
            f"Cursor does not support ${{env:SIS_PORT:-8086}}.",
            file=sys.stderr,
        )
    return written


def claude_command(mcp_config_path, claude_arguments):
    return ["claude", "--strict-mcp-config", "--mcp-config", str(mcp_config_path), *claude_arguments]


def cursor_agent_command(workspace, cursor_arguments, approve_mcps=False):
    """Assemble the cursor-agent argv for a workspace."""
    command = ["cursor-agent", "--workspace", str(workspace)]
    if approve_mcps:
        command.append("--approve-mcps")
    command.extend(cursor_arguments)
    return command


def _warn_if_slot_stopped(layout, slot_number):
    if not is_slot_running(layout, slot_number):
        print(
            f"pds: warning: slot{slot_number} is not running; start it with `pds slot {slot_number} up`",
            file=sys.stderr,
        )


def launch_claude(layout, slot_number, claude_arguments):
    """Replace this process with Claude Code connected to the slot's image."""
    _warn_if_slot_stopped(layout, slot_number)
    command = claude_command(write_slot_mcp_config(layout, slot_number), claude_arguments)
    os.execvp(command[0], command)


def launch_cursor_agent(layout, slot_number, cursor_arguments, workspace=None, approve_mcps=False):
    """Replace this process with Cursor Agent connected to the slot's image."""
    _warn_if_slot_stopped(layout, slot_number)
    workspace_dir = cursor_workspace_dir(workspace)
    write_cursor_mcp_config(layout, workspace_dir)
    command = cursor_agent_command(workspace_dir, cursor_arguments, approve_mcps=approve_mcps)
    os.environ["SIS_PORT"] = str(slot_port(slot_number))
    os.execvp(command[0], command)
