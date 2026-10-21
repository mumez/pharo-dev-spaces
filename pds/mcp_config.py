"""Per-slot MCP configuration for Claude Code and Cursor Agent.

Claude: the smalltalk-dev plugin (>= 2.4.0) reads `${SIS_PORT:-8086}`, so
`pds slot N claude [--workdir DIR]` only sets `SIS_PORT=8086+N` and runs plain
`claude` in DIR (default: cwd), keeping user and project MCP servers. Claude
has no directory flag, so pds changes directory before exec. pds warns when the
installed plugin still has a fixed port.

Cursor: has no --mcp-config flag. It loads `<workdir>/.cursor/mcp.json`.
`pds slot N cursor-agent [--workdir DIR]` uses DIR (default: cwd) as
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

from pds.slot import is_slot_running, slot_port


def cursor_smalltalk_dev_servers():
    """smalltalk-dev MCP servers for Cursor: port from process env via Cursor's `${env:NAME}` expansion."""
    return {
        "smalltalk-interop": {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/mumez/smalltalk-interop-mcp-server.git",
                "smalltalk-interop-mcp-server",
            ],
            "env": {"SIS_PORT": "${env:SIS_PORT}"},
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


def cursor_mcp_config(existing=None):
    """Cursor MCP config: merge pds servers into any existing `.cursor/mcp.json`.

    Existing servers are kept; smalltalk-dev overrides same-named project
    servers. SIS_PORT is `${env:SIS_PORT}` (no `:-default` in Cursor).
    """
    existing = existing or {}
    return {
        **existing,
        "mcpServers": {
            **existing.get("mcpServers", {}),
            **cursor_smalltalk_dev_servers(),
        },
    }


def _read_mcp_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _write_mcp_json(path, config):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n")
    return path


def agent_workdir(workdir=None):
    """Directory the agent works in (`--workdir`, or cwd)."""
    workdir = Path(workdir or os.getcwd()).resolve()
    if not workdir.is_dir():
        raise FileNotFoundError(f"workdir does not exist: {workdir}")
    return workdir


def write_cursor_mcp_config(workdir):
    """Merge pds MCP servers into workdir/.cursor/mcp.json (create if missing)."""
    path = Path(workdir) / ".cursor" / "mcp.json"
    before = path.read_text() if path.exists() else None
    config = cursor_mcp_config(existing=_read_mcp_json(path))
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


def _claude_config_dir():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def installed_smalltalk_dev_plugin_follows_sis_port():
    """Whether every installed smalltalk-dev plugin's `.mcp.json` reads `${SIS_PORT...}` (False if none)."""
    installed_file = _claude_config_dir() / "plugins" / "installed_plugins.json"
    if not installed_file.exists():
        return False
    plugins = json.loads(installed_file.read_text()).get("plugins", {})
    installs = [
        install
        for name, plugin_installs in plugins.items()
        if name.startswith("smalltalk-dev@")
        for install in plugin_installs
    ]
    return bool(installs) and all(
        "${SIS_PORT" in _read_text_or_empty(Path(install["installPath"]) / ".mcp.json") for install in installs
    )


def _read_text_or_empty(path):
    return path.read_text() if path.exists() else ""


def _warn_unless_smalltalk_dev_plugin_follows_sis_port():
    if not installed_smalltalk_dev_plugin_follows_sis_port():
        print(
            "pds: warning: installed smalltalk-dev plugin does not read SIS_PORT (needs >= 2.4.0); "
            "smalltalk-interop may connect to port 8086 instead of this slot. "
            "Update it with `claude plugin update smalltalk-dev@smalltalk-dev-marketplace`.",
            file=sys.stderr,
        )


def cursor_agent_command(workdir, cursor_arguments, approve_mcps=False):
    """Assemble the cursor-agent argv for a workdir."""
    command = ["cursor-agent", "--workspace", str(workdir)]
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


def _exec_with_slot_port(slot_number, command):
    os.environ["SIS_PORT"] = str(slot_port(slot_number))
    os.execvp(command[0], command)


def launch_claude(layout, slot_number, claude_arguments, workdir=None):
    """Replace this process with Claude Code connected to the slot's image, running in the workdir."""
    _warn_if_slot_stopped(layout, slot_number)
    _warn_unless_smalltalk_dev_plugin_follows_sis_port()
    workdir = agent_workdir(workdir)
    os.chdir(workdir)
    _exec_with_slot_port(slot_number, ["claude", *claude_arguments])


def launch_cursor_agent(layout, slot_number, cursor_arguments, workdir=None, approve_mcps=False):
    """Replace this process with Cursor Agent connected to the slot's image."""
    _warn_if_slot_stopped(layout, slot_number)
    workdir = agent_workdir(workdir)
    write_cursor_mcp_config(workdir)
    _exec_with_slot_port(slot_number, cursor_agent_command(workdir, cursor_arguments, approve_mcps=approve_mcps))
