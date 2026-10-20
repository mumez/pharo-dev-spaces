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

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
uv sync
uv run pds setup-plain --version 140   # plain-pharo/: Pharo 14 image + VM
uv run pds prepare-dev-base            # dev-base/: plain + pds/st/load_agentic_browser.st
uv run pds run-dev-base                # optional: open dev-base in the GUI to check it
```

## Registering projects

`projects.json` lists the repositories loaded into snapshots, in load order.

```bash
uv run pds add-project ~/git/MyApp                       # print the entry
uv run pds add-project ~/git/MyApp --write               # append it to projects.json
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
uv run pds slot 2 cursor-agent        # run Cursor Agent with MCP pointed at slot2
uv run pds slot 2 cursor-agent -- -p "/st-eval Smalltalk version"   # arguments after -- go to cursor-agent
uv run pds slot 2 cursor-agent --workspace ./repos/Stick -- -p "fix Stick"
uv run pds slot 2 cursor-agent --approve-mcps --workspace ./repos/Stick -- -p "fix Stick"
uv run pds slot 2 down                # stop
```

`slot N claude` writes `slots/slotN/mcp.json` and runs `claude --strict-mcp-config --mcp-config slots/slotN/mcp.json`.

`slot N cursor-agent [--workspace DIR]` runs `cursor-agent --workspace DIR` (`DIR` defaults to cwd). It merges `smalltalk-interop` / `smalltalk-validator` (plus anything in `mcp_others.json`) into `DIR/.cursor/mcp.json` without dropping other existing servers; on name clashes, `mcp_others.json` and then smalltalk-dev win. `smalltalk-interop` uses `"SIS_PORT": "${env:SIS_PORT}"` (Cursor expands `${env:NAME}` but not `${env:NAME:-default}`); `pds` exports `SIS_PORT=8086+N` on launch and warns when it changes the file. Outside pds, set `SIS_PORT` yourself or expect the server default 8086. `--approve-mcps` is off by default because it auto-approves every MCP server Cursor loads, not only smalltalk; pass `--approve-mcps` to opt in. Arguments after `--` go to `cursor-agent`. Claude still gets a per-slot `slots/slotN/mcp.json` with a concrete port.

Both configs hold the smalltalk-dev plugin's MCP servers (`smalltalk-interop` pointed at the slot's SIS port, and `smalltalk-validator`), merged with any servers you define in `mcp_others.json`:

```json
{ "mcpServers": { "my-server": { "command": "...", "args": ["..."] } } }
```

`status` / `list-slots` include `origin`, recorded by `reset`: `{"source": "snapshots/current", "snapshot": "<date>", "builtAt": "<date>T<time>"}` (the latest `snapshots/<date>.json` manifest at reset time and its `builtAt`; `null` for manifests written before `builtAt` was recorded) or `{"source": "dev-base", "snapshot": null, "builtAt": null}`. It is `null` for a slot that was never reset (or was reset by an older pds).

A slot counts as running only if it was started with `pds slot N up` or `pds slot N gui`, which write a pid file.

## Layout

```
pharo-dev-spaces/
  pds/                  # the CLI (Python) and its .st scripts
  plain-pharo/          # VM + plain image
  dev-base/
  projects.json
  mcp_others.json       # optional
  snapshots/
    current/            # image that slots start from
    <date>.json         # build manifests
  archives/<date>.tar.gz
  slots/slot{1,2,3}/    # Pharo.image/.changes, mcp.json, pharo.pid, pharo.log
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
