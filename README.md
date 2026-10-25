# pharo-dev-spaces

Disposable Pharo images and daily snapshots for AI coding agents.

`pds` is a small CLI that gives each AI coding agent session its own Pharo image, so 2–3 agents can work in parallel without interfering with each other. Every image has [PharoSmalltalkInteropServer (SIS)](https://github.com/mumez/PharoSmalltalkInteropServer) and [AgenticBrowser](https://github.com/mumez/pharo-agentic-browser) loaded. At the end of the day, the `develop` branches of your projects are loaded into a tested snapshot, which becomes the starting point for the next day's slots.

Currently targets Pharo 14, Claude Code, Cursor Agent (CLI), and Linux (WSL).

## Concepts

| Image | Directory | Description |
|---|---|---|
| plain | `plain-pharo/` | Pharo image + VM from get.pharo.org. All images share this VM and its sources file |
| dev-base | `dev-base/` | plain + SIS + AgenticBrowser |
| snapshot | `snapshots/current/` | dev-base (or the previous snapshot) + your projects at `origin/develop`, with all tests passing |
| slot | `slots/slot1..3/` | A disposable copy of the snapshot (or dev-base) for one agent session |

Each image `pds` starts gets its own ports, so images never collide:

| Image | SIS (`PHARO_SIS_PORT`) | Ripple / WebUI (`PHARO_RIPPLE_PORT`) |
|---|---|---|
| standalone (`run-dev-base`) | 8086 | 9086 |
| slot N (1–3) | 8086 + N | 9086 + N |
| snapshot build | 8090 | 9090 |

To move a slot off a port another program already uses, put `slots/slotN/ports.json` next to its image.
Only the keys you write override the defaults (`ripple` still follows `sis` + 1000 unless given):

```json
{ "ripple": 9189 }
```

`pds slot N up` refuses to start when the slot's SIS or Ripple port is already in use.

`pds slot N reset` replaces the image but keeps the slot's `ports.json` and `agentic-browser/` (AgenticBrowser settings saved by that slot).

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
uv sync
uv run pds setup-plain --version 140   # plain-pharo/: Pharo 14 image + VM
uv run pds prepare-dev-base            # dev-base/: plain + pds/st/load_agentic_browser.st
uv run pds run-dev-base                # optional: open dev-base in the GUI to check it
```

## Registering projects

`st-projects.json` lists the repositories loaded into snapshots, in load order.

```bash
uv run pds add-project ~/git/MyApp                       # print the entry
uv run pds add-project ~/git/MyApp --write               # append it to st-projects.json
uv run pds add-project ~/git/MyApp --groups Core,Tests --write
```

`add-project` reads only the BaselineOf name and `srcDirectory` (from `.project`). The packages to load, their order, and the platform-specific parts of the baseline are left to Metacello.

```json
[
  { "repository": "/home/me/git/MyApp", "baseline": "MyApp", "srcDir": "src", "groups": ["default"] }
]
```

## Building snapshots

```bash
uv run pds build-snapshot --full   # first time, or to rebuild from scratch: starts from dev-base
uv run pds build-snapshot          # daily: starts from snapshots/current
```

Both modes:

1. `git fetch` each repository and extract `srcDir` at `origin/develop` into a temporary directory, without touching your working trees.
2. Load each baseline with Metacello (`tonel://<extracted srcDir>`, with its `groups`).
3. Run the tests in the package directories under `srcDir` that are loaded in the image.
4. Only if every test passes: replace `snapshots/current`, write `snapshots/<date>.json` (build time, mode, base, SHA of each repository, test results), and archive the image to `archives/<date>.tar.gz`. If a test fails, `snapshots/current` is left unchanged.

Incremental builds pick up changed methods and baseline changes (new packages or dependencies). Removing or renaming packages and classes is not reflected; run `--full` for that.

## Slots

```bash
uv run pds list-slots                 # status of all slots as JSON; a slot with "running": false is free
uv run pds slot 2 status              # status of one slot
uv run pds slot 2 reset               # recreate slots/slot2 from snapshots/current (or dev-base)
uv run pds slot 2 up                  # start headless (SIS on 8088)
uv run pds slot 2 gui                 # or start with the GUI (pharo-ui) on the same ports
uv run pds slot 2 claude              # run Claude Code with MCP pointed at slot2
uv run pds slot 2 claude -- -p "/st-eval Smalltalk version"   # arguments after -- go to claude
uv run pds slot 2 claude --workdir ./repos/Stick -- -p "fix Stick"
uv run pds slot 2 cursor-agent        # run Cursor Agent with MCP pointed at slot2
uv run pds slot 2 cursor-agent -- -p "/st-eval Smalltalk version"   # arguments after -- go to cursor-agent
uv run pds slot 2 cursor-agent --workdir ./repos/Stick -- -p "fix Stick"
uv run pds slot 2 cursor-agent --approve-mcps --workdir ./repos/Stick -- -p "fix Stick"
uv run pds slot 2 opencode            # run opencode with MCP pointed at slot2
uv run pds slot 2 opencode -- run "/st-eval Smalltalk version"   # arguments after -- go to opencode
uv run pds slot 2 opencode --workdir ./repos/Stick -- run "fix Stick"
uv run pds slot 2 down                # stop
```

`slot N claude [--workdir DIR]` exports `SIS_PORT=8086+N` and runs `claude` in `DIR` (default: cwd). Claude has no directory flag, so pds changes into `DIR` before launching it. The smalltalk-dev plugin (>= [2.4.0](https://github.com/mumez/smalltalk-dev-plugin/releases/tag/v2.4.0)) reads `${SIS_PORT:-8086}`, so its `smalltalk-interop` connects to the slot while your user and project MCP servers stay available. pds warns when the installed plugin still has a fixed port; update it with `claude plugin update smalltalk-dev@smalltalk-dev-marketplace`.

`slot N cursor-agent [--workdir DIR]` runs `cursor-agent --workspace DIR` (`DIR` defaults to cwd). It merges `smalltalk-interop` / `smalltalk-validator` into `DIR/.cursor/mcp.json` without dropping other existing servers; on name clashes, smalltalk-dev wins. `smalltalk-interop` uses `"SIS_PORT": "${env:SIS_PORT}"` (Cursor expands `${env:NAME}` but not `${env:NAME:-default}`); `pds` exports `SIS_PORT=8086+N` on launch and warns when it changes the file. Outside pds, set `SIS_PORT` yourself or expect the server default 8086. `--approve-mcps` is off by default because it auto-approves every MCP server Cursor loads, not only smalltalk; pass `--approve-mcps` to opt in. Arguments after `--` go to `cursor-agent`. Other MCP servers come from your user-level `~/.cursor/mcp.json` as usual.

`slot N opencode [--workdir DIR]` merges `smalltalk-interop` / `smalltalk-validator` into `DIR/opencode.json` (`DIR` defaults to cwd) without dropping other existing servers; on name clashes, smalltalk-dev wins. `smalltalk-interop` uses `"SIS_PORT": "{env:SIS_PORT}"` (opencode expands `{env:NAME}`); `pds` exports `SIS_PORT=8086+N` on launch and warns when it changes the file. Outside pds, set `SIS_PORT` yourself or expect the server default 8086. opencode has no directory flag, so pds changes into `DIR` before launching it. Arguments after `--` go to `opencode` (e.g. `run "..."` for non-interactive mode). Other MCP servers come from your `~/.config/opencode/opencode.json` as usual.

`status` / `list-slots` include `origin`, recorded by `reset`: `{"source": "snapshots/current", "snapshot": "<date>", "builtAt": "<date>T<time>"}` (the latest `snapshots/<date>.json` manifest at reset time and its `builtAt`; `null` for manifests written before `builtAt` was recorded) or `{"source": "dev-base", "snapshot": null, "builtAt": null}`. It is `null` for a slot that was never reset (or was reset by an older pds).

A slot counts as running only if it was started with `pds slot N up` or `pds slot N gui`, which write a pid file.

## Layout

```
pharo-dev-spaces/
  pds/                  # the CLI (Python) and its .st scripts
  plain-pharo/          # VM + plain image
  dev-base/
  st-projects.json
  snapshots/
    current/            # image that slots start from
    <date>.json         # build manifests
  archives/<date>.tar.gz
  slots/slot{1,2,3}/    # Pharo.image/.changes, pharo.pid, pharo.log
```

Everything except `pds/`, `tests/`, and `tasks/` is generated and ignored by git. Set `PDS_ROOT` to use a different root directory.

## Development

```bash
uv run pytest            # unit tests
uv run pytest -m pharo   # integration tests that launch a real Pharo (needs plain-pharo/ and dev-base/)
```

## License

MIT

Past implementation plans are kept in `tasks/archive/`.
