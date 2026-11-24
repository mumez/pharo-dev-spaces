"""Per-slot MCP configuration for Claude Code and Cursor Agent.

Claude: the smalltalk-dev plugin (>= 2.4.0) reads `${SIS_PORT:-8086}`, so
`pds slot N claude [--workdir DIR]` only sets `SIS_PORT` to the slot's SIS port and runs plain
`claude` in DIR (default: cwd), keeping user and project MCP servers. Claude
has no directory flag, so pds changes directory before exec. pds warns when the
installed plugin still has a fixed port.

Cursor: loads `<workdir>/.cursor/mcp.json`.
`pds slot N cursor-agent [--workdir DIR]` uses DIR (default: cwd) as
`cursor-agent --workspace`, merges smalltalk servers into that directory's
`.cursor/mcp.json` with `"SIS_PORT": "${env:SIS_PORT}"`, and sets
`SIS_PORT` to the slot's SIS port in the process environment. Cursor does not support
`${env:NAME:-default}`, so opening the project outside pds may leave an unset
SIS_PORT; pds warns when it changes the file.

opencode: loads `<workdir>/opencode.json`.
`pds slot N opencode [--workdir DIR]` uses DIR (default: cwd), merges smalltalk
servers into that directory's `opencode.json` with
`"SIS_PORT": "{env:SIS_PORT}"` (opencode uses single-brace `{env:NAME}`
expansion), and sets `SIS_PORT` to the slot's SIS port in the process environment. opencode has
no directory flag, so pds changes directory before exec. pds warns when it
changes the file.

agy: loads `<workdir>/.agents/mcp_config.json`.
`pds slot N agy [--workdir DIR]` uses DIR (default: cwd), merges smalltalk
servers into that directory's `.agents/mcp_config.json` with
`"SIS_PORT": "<port>"`, and sets `SIS_PORT=8086+N` in the process environment.
Antigravity does not expand environment variables in MCP configs, so the port
is baked into the config directly. agy has no directory flag, so pds changes
directory before exec. pds warns when it changes the file.
"""

SMALLTALK_INTEROP = "git+https://github.com/mumez/smalltalk-interop-mcp-server.git"
SMALLTALK_VALIDATOR = "git+https://github.com/mumez/smalltalk-validator-mcp-server.git@main"

import json
import os
import sys
from pathlib import Path

from pds.slot import is_slot_running, slot_ports


def _stdio_smalltalk_dev_servers(sis_port=None):
    """Stdio smalltalk-dev MCP servers (used by Cursor and agy)."""
    server = {
        "command": "uvx",
        "args": ["--from", SMALLTALK_INTEROP, "smalltalk-interop-mcp-server"],
    }
    if sis_port is not None:
        server["env"] = {"SIS_PORT": str(sis_port)}
    return {
        "smalltalk-interop": server,
        "smalltalk-validator": {
            "command": "uvx",
            "args": ["--from", SMALLTALK_VALIDATOR, "smalltalk-validator-mcp-server"],
        },
    }


def cursor_smalltalk_dev_servers():
    """smalltalk-dev MCP servers for Cursor: port from process env via Cursor's `${env:NAME}` expansion."""
    return _stdio_smalltalk_dev_servers("${env:SIS_PORT}")


def opencode_smalltalk_dev_servers():
    """smalltalk-dev MCP servers for opencode: port from process env via opencode's `{env:NAME}` expansion."""
    return {
        "smalltalk-interop": {
            "type": "local",
            "command": ["uvx", "--from", SMALLTALK_INTEROP, "smalltalk-interop-mcp-server"],
            "environment": {"SIS_PORT": "{env:SIS_PORT}"},
        },
        "smalltalk-validator": {
            "type": "local",
            "command": ["uvx", "--from", SMALLTALK_VALIDATOR, "smalltalk-validator-mcp-server"],
        },
    }


def agy_smalltalk_dev_servers(sis_port=None):
    """smalltalk-dev MCP servers for Antigravity CLI.

    Antigravity does not expand environment variables in MCP configs, so the port
    is embedded literally rather than using env interpolation.
    """
    return _stdio_smalltalk_dev_servers(sis_port)


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


def opencode_mcp_config(existing=None):
    """opencode MCP config: merge pds servers into any existing `opencode.json`.

    Existing servers are kept; smalltalk-dev overrides same-named project
    servers. SIS_PORT is `{env:SIS_PORT}`.
    """
    existing = existing or {}
    return {
        **existing,
        "mcp": {
            **existing.get("mcp", {}),
            **opencode_smalltalk_dev_servers(),
        },
    }


def agy_mcp_config(existing=None, sis_port=None):
    """Antigravity CLI MCP config: merge pds servers into any existing `.agents/mcp_config.json`.

    Existing servers are kept; smalltalk-dev overrides same-named project
    servers. SIS_PORT is set to the slot's SIS port.
    """
    existing = existing or {}
    return {
        **existing,
        "mcpServers": {
            **existing.get("mcpServers", {}),
            **agy_smalltalk_dev_servers(sis_port=sis_port),
        },
    }


def _skip_jsonc_comment(text, i):
    """Index just past a `//` or `/* */` comment starting at i (i itself when there is none)."""
    if text.startswith("//", i):
        end = text.find("\n", i)
        return len(text) if end == -1 else end
    if text.startswith("/*", i):
        end = text.find("*/", i + 2)
        return len(text) if end == -1 else end + 2
    return i


def _skip_jsonc_ws_and_comments(text, i):
    while i < len(text):
        if text[i] in " \t\r\n":
            i += 1
            continue
        after_comment = _skip_jsonc_comment(text, i)
        if after_comment == i:
            break
        i = after_comment
    return i


def _jsonc_to_json(text):
    """Strip JSONC comments and trailing commas so strict `json.loads` can parse them."""
    out = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            i += 1
        elif c == '"':
            in_string = True
            out.append(c)
            i += 1
        elif (after_comment := _skip_jsonc_comment(text, i)) != i:
            i = after_comment
        elif c == ",":
            j = _skip_jsonc_ws_and_comments(text, i + 1)
            if j < n and text[j] in "}]":
                i += 1
            else:
                out.append(c)
                i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _read_mcp_json(path):
    if not path.exists():
        return {}
    return json.loads(_jsonc_to_json(path.read_text()))


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


def _merge_smalltalk_dev_servers(workdir, config_relpath, build_config, warning_template):
    """Merge smalltalk MCP servers into workdir/<config_relpath>, warning when the file changes.

    Refuses when the config path, or any directory on the way to it, is a symlink
    resolving outside the workdir, so a repo-provided symlink cannot rewrite a file
    outside it (e.g. the user's global opencode.json).
    """
    path = Path(workdir) / config_relpath
    if not path.resolve().is_relative_to(Path(workdir).resolve()):
        raise FileExistsError(
            f"pds: refusing to merge into {path}: a symlink resolves it outside the workdir; "
            "remove it or point it inside the workdir"
        )
    before = path.read_text() if path.exists() else None
    config = build_config(existing=_read_mcp_json(path))
    written = _write_mcp_json(path, config)
    after = written.read_text()
    if before != after:
        print(warning_template.format(path=path), file=sys.stderr)
    return written


def write_cursor_mcp_config(workdir):
    """Merge pds MCP servers into workdir/.cursor/mcp.json (create if missing)."""
    return _merge_smalltalk_dev_servers(
        workdir,
        Path(".cursor") / "mcp.json",
        cursor_mcp_config,
        "pds: warning: merged smalltalk MCP servers into {path} "
        "(SIS_PORT=${{env:SIS_PORT}}); outside pds set SIS_PORT or expect port 8086. "
        "Cursor does not support ${{env:SIS_PORT:-8086}}.",
    )


def write_opencode_mcp_config(workdir):
    """Merge pds MCP servers into workdir/opencode.json (create if missing)."""
    return _merge_smalltalk_dev_servers(
        workdir,
        Path("opencode.json"),
        opencode_mcp_config,
        "pds: warning: merged smalltalk MCP servers into {path} "
        "(SIS_PORT={{env:SIS_PORT}}); outside pds set SIS_PORT or expect port 8086.",
    )


def write_agy_mcp_config(workdir, sis_port=None):
    """Merge pds MCP servers into workdir/.agents/mcp_config.json (create if missing)."""
    warning = (
        f"pds: warning: merged smalltalk MCP servers into {{path}} (SIS_PORT={sis_port}); "
        f"outside pds expect port {sis_port}."
        if sis_port is not None
        else "pds: warning: merged smalltalk MCP servers into {path}."
    )
    return _merge_smalltalk_dev_servers(
        workdir,
        Path(".agents") / "mcp_config.json",
        lambda existing: agy_mcp_config(existing, sis_port=sis_port),
        warning,
    )


def _claude_config_dir():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def installed_smalltalk_dev_plugin_follows_sis_port():
    """Whether every installed smalltalk-dev plugin's `.mcp.json` reads `${SIS_PORT...}`.

    Best-effort: `installed_plugins.json` is owned by Claude, so a missing,
    unreadable, or unexpectedly shaped file yields False instead of raising.
    """
    installed_file = _claude_config_dir() / "plugins" / "installed_plugins.json"
    try:
        plugins = json.loads(installed_file.read_text()).get("plugins", {})
        installs = [
            install
            for name, plugin_installs in plugins.items()
            if name.startswith("smalltalk-dev@")
            for install in plugin_installs
        ]
        return bool(installs) and all(
            "${SIS_PORT" in (Path(install["installPath"]) / ".mcp.json").read_text() for install in installs
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


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


def _exec_with_slot_port(layout, slot_number, command):
    os.environ["SIS_PORT"] = str(slot_ports(layout, slot_number)["sis"])
    os.execvp(command[0], command)


def launch_opencode(layout, slot_number, opencode_arguments, workdir=None):
    """Replace this process with opencode connected to the slot's image, running in the workdir."""
    _warn_if_slot_stopped(layout, slot_number)
    workdir = agent_workdir(workdir)
    write_opencode_mcp_config(workdir)
    os.chdir(workdir)
    _exec_with_slot_port(layout, slot_number, ["opencode", *opencode_arguments])


def launch_agy(layout, slot_number, agy_arguments, workdir=None):
    """Replace this process with Antigravity CLI connected to the slot's image, running in the workdir."""
    _warn_if_slot_stopped(layout, slot_number)
    workdir = agent_workdir(workdir)
    sis_port = slot_ports(layout, slot_number)["sis"]
    write_agy_mcp_config(workdir, sis_port=sis_port)
    os.chdir(workdir)
    _exec_with_slot_port(layout, slot_number, ["agy", *agy_arguments])


def launch_claude(layout, slot_number, claude_arguments, workdir=None):
    """Replace this process with Claude Code connected to the slot's image, running in the workdir."""
    _warn_if_slot_stopped(layout, slot_number)
    _warn_unless_smalltalk_dev_plugin_follows_sis_port()
    workdir = agent_workdir(workdir)
    os.chdir(workdir)
    _exec_with_slot_port(layout, slot_number, ["claude", *claude_arguments])


def launch_cursor_agent(layout, slot_number, cursor_arguments, workdir=None, approve_mcps=False):
    """Replace this process with Cursor Agent connected to the slot's image."""
    _warn_if_slot_stopped(layout, slot_number)
    workdir = agent_workdir(workdir)
    write_cursor_mcp_config(workdir)
    _exec_with_slot_port(
        layout, slot_number, cursor_agent_command(workdir, cursor_arguments, approve_mcps=approve_mcps)
    )
