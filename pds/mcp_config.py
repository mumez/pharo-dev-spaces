"""Per-slot MCP configuration for `claude --strict-mcp-config`.

--strict-mcp-config also hides the smalltalk-dev plugin's own servers (fixed to SIS_PORT 8086),
so the slot config redefines them with the slot's port and merges mcp_others.json for anything else.
"""

import json
import os
import sys

from pds.slot import is_slot_running, slot_dir, slot_port


def smalltalk_dev_servers(sis_port):
    """Same servers as the smalltalk-dev plugin's .mcp.json, pointed at `sis_port`."""
    return {
        "smalltalk-interop": {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/mumez/smalltalk-interop-mcp-server.git",
                "smalltalk-interop-mcp-server",
            ],
            "env": {"SIS_PORT": str(sis_port)},
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


def other_servers(layout):
    if not layout.mcp_others_file.exists():
        return {}
    return json.loads(layout.mcp_others_file.read_text()).get("mcpServers", {})


def slot_mcp_config(layout, slot_number):
    return {"mcpServers": {**other_servers(layout), **smalltalk_dev_servers(slot_port(slot_number))}}


def write_slot_mcp_config(layout, slot_number):
    path = slot_dir(layout, slot_number) / "mcp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(slot_mcp_config(layout, slot_number), indent=2) + "\n")
    return path


def claude_command(mcp_config_path, claude_arguments):
    return ["claude", "--strict-mcp-config", "--mcp-config", str(mcp_config_path), *claude_arguments]


def launch_claude(layout, slot_number, claude_arguments):
    """Replace this process with Claude Code connected to the slot's image."""
    if not is_slot_running(layout, slot_number):
        print(f"pds: warning: slot{slot_number} is not running; start it with `pds slot up {slot_number}`", file=sys.stderr)
    command = claude_command(write_slot_mcp_config(layout, slot_number), claude_arguments)
    os.execvp(command[0], command)
