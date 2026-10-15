"""Per-slot MCP configuration for Claude Code and Cursor Agent.

Claude: `claude --strict-mcp-config --mcp-config slots/slotN/mcp.json` with a
concrete SIS_PORT so the smalltalk-dev plugin's servers (fixed to 8086) are hidden.

Cursor: has no --mcp-config flag. It loads `<projectRoot>/.cursor/mcp.json` and
expands `${env:NAME}` in env values. The Cursor config therefore uses
`${env:SIS_PORT}` (slot-independent, safe to share across concurrent agents on
the same project), and `launch_cursor_agent` sets SIS_PORT in the process env.

`pds slot N cursor-agent --project DIR`:
- if DIR is its own git root (and not the pds root): use DIR as --workspace and
  write DIR/.cursor/mcp.json (e.g. repos/Stick);
- otherwise: use ~/.cache/pharo-dev-spaces/slotN as --workspace (outside any git
  tree) and --add-dir DIR so the agent can still edit the project.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from pds.slot import is_slot_running, slot_dir, slot_port


def _smalltalk_dev_servers(sis_port_value):
    """smalltalk-dev MCP servers; `sis_port_value` is either a port string or `${env:SIS_PORT}`."""
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
    """Cursor form: port comes from the agent process env (supports concurrent slots)."""
    return _smalltalk_dev_servers("${env:SIS_PORT}")


def other_servers(layout):
    if not layout.mcp_others_file.exists():
        return {}
    return json.loads(layout.mcp_others_file.read_text()).get("mcpServers", {})


def slot_mcp_config(layout, slot_number):
    """Claude: concrete SIS_PORT for slots/slotN/mcp.json."""
    return {"mcpServers": {**other_servers(layout), **smalltalk_dev_servers(slot_port(slot_number))}}


def cursor_mcp_config(layout, existing=None):
    """Cursor MCP config: merge pds servers into any existing `.cursor/mcp.json`.

    Existing servers are kept. `mcp_others.json` and the smalltalk-dev servers are
    layered on top (smalltalk-dev wins on name clashes). SIS_PORT uses
    `${env:SIS_PORT}` so one file works for every slot.
    """
    existing = existing or {}
    existing_servers = existing.get("mcpServers", {})
    return {
        **existing,
        "mcpServers": {**existing_servers, **other_servers(layout), **cursor_smalltalk_dev_servers()},
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


def cursor_agent_cache_workspace_dir(slot_number):
    """Fallback --workspace outside any git tree (per-slot MCP isolation)."""
    slot_port(slot_number)
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_home / "pharo-dev-spaces" / f"slot{slot_number}"


# Kept as an alias so older tests/imports keep working.
cursor_agent_workspace_dir = cursor_agent_cache_workspace_dir


def git_toplevel(path):
    """Absolute git toplevel for `path`, or None if not inside a work tree."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return Path(completed.stdout.strip()).resolve()


def resolve_cursor_agent_paths(layout, slot_number, project=None):
    """Return (workspace, add_dir) for cursor-agent.

    add_dir is None when the project itself is the workspace.
    """
    project_dir = Path(project or os.getcwd()).resolve()
    if not project_dir.is_dir():
        raise FileNotFoundError(f"project directory does not exist: {project_dir}")
    toplevel = git_toplevel(project_dir)
    if toplevel == project_dir and project_dir != layout.root.resolve():
        return project_dir, None
    return cursor_agent_cache_workspace_dir(slot_number), project_dir


def write_cursor_mcp_config(layout, workspace):
    """Merge pds MCP servers into workspace/.cursor/mcp.json (create if missing)."""
    path = Path(workspace) / ".cursor" / "mcp.json"
    return _write_mcp_json(path, cursor_mcp_config(layout, existing=_read_mcp_json(path)))


def write_slot_cursor_mcp_config(layout, slot_number):
    """Write MCP config into the per-slot cache workspace (used when project is not a git root)."""
    return write_cursor_mcp_config(layout, cursor_agent_cache_workspace_dir(slot_number))


def claude_command(mcp_config_path, claude_arguments):
    return ["claude", "--strict-mcp-config", "--mcp-config", str(mcp_config_path), *claude_arguments]


def cursor_agent_command(workspace, cursor_arguments, add_dir=None):
    """Assemble the cursor-agent argv for a resolved workspace / optional add-dir."""
    command = ["cursor-agent", "--workspace", str(workspace), "--approve-mcps"]
    if add_dir is not None and Path(add_dir).resolve() != Path(workspace).resolve():
        command.extend(["--add-dir", str(add_dir)])
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


def launch_cursor_agent(layout, slot_number, cursor_arguments, project=None):
    """Replace this process with Cursor Agent connected to the slot's image."""
    _warn_if_slot_stopped(layout, slot_number)
    workspace, add_dir = resolve_cursor_agent_paths(layout, slot_number, project=project)
    write_cursor_mcp_config(layout, workspace)
    command = cursor_agent_command(workspace, cursor_arguments, add_dir=add_dir)
    os.environ["SIS_PORT"] = str(slot_port(slot_number))
    os.execvp(command[0], command)
