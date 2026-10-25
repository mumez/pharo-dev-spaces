---
name: pharo-dev-spaces
description: Operate pharo-dev-spaces (`pds`) at $PDS_HOME — build the Pharo base image (plain + dev-base), register Smalltalk projects (local repos or GitHub URLs cloned into repos/), build/rebuild daily snapshots, and reset/start slots and launch a coding agent (claude / cursor-agent / opencode) against a slot. Use this whenever the user mentions pds, pharo-dev-spaces, slots ("スロット"), snapshots ("スナップショット"), the base image / dev-base ("ベースイメージ"), st-projects.json, or asks things like "pdsのプロジェクトに追加して", "スナップショットを作成して", "ベースイメージをPharo 14で作成して", "スロット2をリセットして作業して", "空いているスロットで作業を開始して", even if they don't say "pds" explicitly but are clearly talking about Pharo images for agent sessions.
---

# pharo-dev-spaces (pds)

`pds` gives each AI coding agent session its own disposable Pharo image ("slot").
Images build on each other:

| Image | Directory (under `$PDS_HOME`) | Built by |
|---|---|---|
| plain | `plain-pharo/` (VM + image; **every image shares this VM**) | `pds setup-plain --version 140` |
| dev-base | `dev-base/` (plain + SIS + AgenticBrowser) | `pds prepare-dev-base` |
| snapshot | `snapshots/current/` (+ `snapshots/<date>.json` manifests) | `pds build-snapshot [--full]` |
| slot N (1–5) | `slots/slotN/` (copy of snapshot, or dev-base if none) | `pds slot N reset` |

Slot N listens on SIS port `8086+N` (Ripple `9086+N`) unless `slots/slotN/ports.json` overrides it.
`$PDS_HOME/README.md` is the authoritative reference; read it when something here is unclear.

## Running pds

- `$PDS_HOME` points at the pharo-dev-spaces checkout. Check it once (`echo "$PDS_HOME"`); if it is
  empty or the directory has no `pyproject.toml`, ask the user for the path rather than guessing.
- Run every command as `uv run --project "$PDS_HOME" pds <command>` (below abbreviated `pds`).
  This works from any cwd. If `PDS_ROOT` is set, pds uses that as the root instead of `$PDS_HOME`;
  mention it to the user if the two differ.
- Start with the state, not assumptions: `pds list-slots` (JSON per slot: `running`, `hasImage`,
  `port`, `origin`), and `ls "$PDS_HOME"` / `cat "$PDS_HOME/st-projects.json"` for the rest.
- `prepare-dev-base` (≤30 min) and `build-snapshot` (≤60 min) are long. Run them in the background
  with output going to `$PDS_HOME/logs/<command>-<YYYYMMDD-HHMM>.log` (`mkdir -p` it first), then
  read the log when the command finishes, instead of letting a foreground call time out.

## Base image — "ベースイメージをPharo 14で作成して"

Pharo version → `--version`: Pharo 14 → `140`, Pharo 13 → `130` (digits only).

```bash
pds setup-plain --version 140      # plain-pharo/
pds prepare-dev-base               # dev-base/ (loads SIS + AgenticBrowser)
```

- If `plain-pharo/` or `dev-base/` already exists, the command refuses. Replacing needs `--force`,
  which deletes the old one — confirm with the user first, and say which Pharo version is there now
  (`ls $PDS_HOME/plain-pharo`, or the image's version if visible).
- Before `setup-plain --force`, check `pds list-slots`: running slots use the shared VM, so stop
  them (or ask) first.
- A new dev-base invalidates the existing snapshot and slots (they were built on the old base).
  Afterwards, suggest `pds build-snapshot --full` and resetting slots.

## Registering projects — "～をpdsのプロジェクトに追加して"

`st-projects.json` lists repositories loaded into snapshots, in load order.

1. Get a local repository path:
   - Local path (e.g. `~/git/MyApp`): use it as is (absolute path).
   - Git URL: clone into `$PDS_HOME/repos/<repo-name>` (`git clone <url> "$PDS_HOME/repos/<name>"`).
     If that directory already exists, don't overwrite it — check whether it is the same remote and
     reuse it, otherwise ask.
2. Check the snapshot prerequisite: `build-snapshot` loads **`origin/develop`**, so run
   `git -C <repo> ls-remote --heads origin develop`. If there's no `origin` or no `develop`
   branch, still register the project but tell the user that snapshot builds will fail until it
   exists. Do not create or push branches on the remote yourself.
3. Register:
   ```bash
   pds add-project <repo-path> --write                      # groups default to "default"
   pds add-project <repo-path> --groups Core,Tests --write  # when the user names groups
   ```
   It reads the `BaselineOf*` name and `srcDirectory` (from `.project`). "no BaselineOf* package"
   means it is not a Tonel/Metacello project — report that. "already in st-projects.json" means
   nothing to do.
4. Show the resulting entry, and mention that the project enters slots only after the next
   `pds build-snapshot`.

## Snapshots — "スナップショットを作成して"

```bash
pds build-snapshot          # incremental: starts from snapshots/current (daily use)
pds build-snapshot --full   # starts from dev-base
```

Choose `--full` when `snapshots/current/` doesn't exist yet, after dev-base was rebuilt, or when
the user says packages/classes were removed or renamed (incremental builds can't drop them).
Otherwise use incremental. Requires `dev-base/` and a non-empty `st-projects.json`.

The build fetches `origin/develop` of each project (working trees untouched), loads baselines,
runs their tests, and promotes the image only if every test passes. On success report the new
`snapshots/<date>.json` (repositories + SHAs, test counts). On failure `snapshots/current` is
unchanged — report the failing tests or git error from the output; don't retry blindly.

Running slots keep their old image; a slot only picks up the new snapshot on `reset`.

## Slots and starting work

### Choosing the slot

- Named slot ("スロット2"): use it.
- "空いているスロット": `pds list-slots` and take the lowest-numbered slot with `"running": false`.
  If all 5 are running, tell the user and stop. If `pds slot N up` later fails because a port is
  in use by another program, move on to the next free slot.

### Preparing it

- "リセットして" or the slot has no image (`hasImage: false`): `pds slot N reset`. Reset refuses
  while running; `pds slot N down` first only if the user asked to reset that specific slot
  (a running slot may be another agent's session — never stop one you merely picked as "free").
- A free slot is stale when its `origin.builtAt` is older than the `builtAt` in the newest
  `snapshots/<date>.json` (compare times, not dates — a snapshot can be rebuilt on the same day),
  or when `origin` is `null` / from dev-base while a snapshot exists. Reset it too, and say so.
- Start it: `pds slot N up` (headless) or `pds slot N gui` if the user wants the Pharo GUI.
  Then wait until the SIS port listens (`ss -ltn | grep ":<port> "`, a few seconds);
  `slots/slotN/pharo.log` shows startup errors.

### Which agent

Launch the same kind of agent you are: Claude Code → `claude`, Cursor Agent → `cursor-agent`,
opencode → `opencode`. If you are something else, or the user named one, follow the user; if
unsupported, ask which of the three to use.

The working directory (`--workdir`) should be a Smalltalk project repository, because that is where
the child agent edits Tonel files. Pick the first that applies and pass it as an absolute path:

1. The repo the user named (or the matching `repository` in `st-projects.json`).
2. The cwd pds was invoked from, if it is a project repo (not `$PDS_HOME` itself).
3. Otherwise a repository from `st-projects.json` (e.g. `$PDS_HOME/repos/<name>`): use it if there
   is only one; if there are several, show the command with one of them and list the others.

`$PDS_HOME` itself is never a good workdir — it holds the pds tool, not Smalltalk code.

### Starting work

This depends on whether the user gave a concrete task.

**Task given** (e.g. "スロット2でStickのバグを直して") → run the agent non-interactively yourself:

```bash
pds slot N claude --workdir <dir> -- -p "<task>" --permission-mode acceptEdits
pds slot N cursor-agent --workdir <dir> -- -p "<task>"
pds slot N opencode --workdir <dir> -- run "<task>"
```

Everything after `--` goes to the agent. Write the task as a self-contained prompt (the child
agent has none of your context). Run it in the background with output to
`$PDS_HOME/slots/slotN/agent.log`, and when it finishes, summarise what it did. Don't add
permission-bypassing flags (e.g. `--dangerously-skip-permissions`, `--approve-mcps`) unless the user
asked; if the log shows permission denials, report them and let the user decide.

**No task given** ("スロット2で作業を開始して") → an interactive session can't be opened from
inside your session (pds `exec`s the agent, and your own MCP connection stays on its original
port). Prepare and start the slot, then give the user the command to run in their terminal:

```bash
uv run --project "$PDS_HOME" pds slot N claude --workdir <dir>
```

### Other slot commands

`pds slot N status` (JSON), `pds slot N down` (stop). When you started a slot only to run a
non-interactive task, leave it running unless the user asked to stop it — they may want to
inspect the image.

## Reporting

End with a short summary: what was run, the resulting state (e.g. slot number, SIS port,
snapshot date, registered entry), and anything the user must do next (e.g. "create a develop
branch", "run this command to start the session").
