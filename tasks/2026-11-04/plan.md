# Implementation Plan: Overlay a remote branch onto a slot

## Overview

Copy `snapshots/current` into a slot, Metacello-load only the named repositories at `origin/<branch>`, and run the same project test suite as `build-snapshot`. This is the review flow for RepoA `feature/xxx` in slot 1:

```bash
uv run pds slot 1 reset --ref RepoA:feature/xxx
uv run pds slot 1 up
```

`up` and `gui` stay process launchers. Tests run as part of producing the slot image, on the same side of the command as `build-snapshot`.

## Command

Add these options to `pds slot N reset`.

| Option | Meaning |
|---|---|
| `--ref NAME:BRANCH` | Repeatable. After copying the snapshot, overlay that repository at `origin/BRANCH`. The set passed on this command becomes the slot's entire saved ref list |
| `--load` | Overlay the refs saved in `slots/slotN/refs.json` |
| `--test` / `--no-test` | Run the project tests after an overlay. Omitting the flag runs them |
| `--clear-refs` | Drop the saved refs and recreate a clean copy of the snapshot (or dev-base, when no snapshot exists) |

`--ref` performs the overlay. When `--ref` and `--load` are both present, the `--ref` set is the one that is loaded.

### Combinations

| Command | Image | `refs.json` | Tests |
|---|---|---|---|
| `reset` | Today's copy | Kept | No |
| `reset --no-test` | Today's copy | Kept | No |
| `reset --ref RepoA:feature/xxx` | Overlay | Replaced with this one entry | Yes |
| `reset --ref RepoA:feature/xxx --ref RepoB:feature/yyy` | Overlay both | Replaced with these two entries | Yes |
| `reset --ref RepoA:feature/xxx --test` | Overlay | Replaced | Yes |
| `reset --ref RepoA:feature/xxx --no-test` | Overlay | Replaced | No |
| `reset --load` | Overlay the saved refs | Contents unchanged | Yes |
| `reset --load --no-test` | Overlay the saved refs | Contents unchanged | No |
| `reset --clear-refs` | Clean copy | Deleted. Success when the file was already absent | No |

Reject the following before doing any work. Leave the image and `refs.json` unchanged. Write nothing to stdout, write `pds: ...` to stderr, and exit 1.

- The slot is running. Use the current reset message, which tells the user to run `down`.
- `--test` without `--ref` and without `--load`.
- `--clear-refs` together with `--ref` or `--load`.
- `--load` when `refs.json` is absent.
- A `--ref` that is not `NAME:BRANCH`, an empty `NAME` or `BRANCH`, or the same repository given twice.
- A `NAME` that matches zero or more than one entry in `st-projects.json`.
- A `refs.json` that does not match the schema below, or whose `repository` is not in `st-projects.json`.

Distinguish an omitted `--test` from an explicit `--test`. Use `BooleanOptionalAction` with default `None`. Both `None` and `--test` (`True`) run tests on an overlay. `--no-test` skips them. A reset that does not overlay, left at `None`, does not run tests.

## Overlay

The base image is `snapshots/current` only. When that image is missing, do not replace the slot. Return the `loaded: false` JSON from the exit-code section and tell the user to run `pds build-snapshot --full`. A reset with no overlay options still copies dev-base when no snapshot exists.

Use the same mechanism as an incremental `build-snapshot` load.

1. `git fetch origin <branch>` for each named repository in `st-projects.json`, and archive `srcDir` at `origin/<branch>`. Do not checkout the working tree.
2. Copy `snapshots/current` into the slot.
3. Metacello `get` and `load` only those repositories, through the existing `load_baselines.st`. Keep `baseline`, `srcDir`, and `groups` from `st-projects.json`.
4. Leave every other repository as it was built into the snapshot. Do not fetch it again and do not load it again. Each repository's snapshot branch is the `branch` in `st-projects.json`, or `develop` when `branch` is omitted.
5. Start Pharo once. The script loads the named repositories and, only when tests are requested, continues with `run_tests.st`. Use the `build-snapshot` timeout and SIS port (3600 seconds, 8096). When that port is in use, do not replace the image.
6. The process save happens when that script exits. Promote the staging directory to the slot only when the script has exited and, if tests were requested, the results file exists. Remove the Iceberg cache before promoting.

`BRANCH` is a branch name on origin. A value passed with an `origin/` prefix, either as `--ref` or as `ref` in `refs.json`, is the same branch with that prefix removed. SHAs and branches that exist only locally are out of scope.

Resolve `NAME` in this order and stop at the first unique match:

1. `baseline`
2. The directory name of the repository path
3. The absolute repository path

### Test scope

Match `build-snapshot`. Run the tests in the package directories directly under each `srcDir` from `st-projects.json` that are loaded in the image. Skip `BaselineOf*` and names starting with `.`. SIS and AgenticBrowser are loaded into dev-base by `load_agentic_browser.st`, not from a project `srcDir`, so their packages are outside this list. Registering one of those repositories in `st-projects.json` tests it like any other project.

Collect package names as follows:

- For an overlaid repository, list the `srcDir` fetched for this run.
- For every other repository, `git archive` the `sha` recorded for it in the latest `snapshots/<date>.json`. Do not fetch `origin/<branch>` again.
- When the manifest has no `sha`, the object is not present locally, or a `st-projects.json` repository is absent from the manifest, fail without replacing the image.

A failed test suite still leaves the loaded image in the slot. `build-snapshot` leaves `snapshots/current` unchanged on failure; a slot is the place to inspect that failure with `up` or `gui`, so the slot image stays. Report the failure with exit code 1 and the `tests` object in the JSON.

## Saved refs

`slots/slotN/refs.json` remembers the refs the next `--load` will use. It survives reset, as `ports.json` does. It is not merged with `st-projects.json`.

```json
[
  {"repository": "/home/me/git/RepoA", "ref": "feature/xxx"}
]
```

- Each element has only `repository` and `ref`. Unknown keys are rejected.
- `repository` matches the absolute path written in `st-projects.json`.
- `ref` is a branch name without the `origin/` prefix.
- The file does not store a SHA. The SHA that was actually loaded is written to `origin.json`.
- A successful `--ref` load replaces this file with the set that was passed. A failed test suite still updates it, because the image contains those refs.
- A fetch or Metacello failure leaves the file unchanged.
- `--load` reads the file and fetches again. A branch that has moved is loaded at its new SHA. The file contents stay as they were.
- Editing the file by hand and then running `--load` is supported.
- `--clear-refs` deletes the file only when the clean reset succeeds. A failed replacement leaves it in place.

## Records and status

A reset with no overlay writes `origin.json` in its current shape:

```json
{"source": "snapshots/current", "snapshot": "2026-11-04", "builtAt": "2026-11-04T09:00:00"}
```

A successful overlay adds `refs`:

```json
{
  "source": "snapshots/current",
  "snapshot": "2026-11-04",
  "builtAt": "2026-11-04T09:00:00",
  "refs": [
    {
      "repository": "/home/me/git/RepoA",
      "baseline": "RepoA",
      "ref": "feature/xxx",
      "sha": "abcdef"
    }
  ]
}
```

`ref` has no `origin/` prefix. `sha` is the commit archived by this run.

When tests ran, write the result to `slots/slotN/tests.json`. The object matches the snapshot manifest's `tests`: `run`, `passed`, `failures`, and `errors`. Delete the temporary file Pharo writes after reading it. `tests.json` does not survive reset. `--no-test` does not create it.

`pds slot N status` and `pds list-slots` always add:

- `savedRefs`: the `refs.json` array, or `[]` when the file is absent.
- `tests`: the `tests.json` object, or `null` when the file is absent.

`origin.refs` is what this image contains. `savedRefs` is what the next `--load` will use. After a clean reset, `origin` has no `refs` key and `savedRefs` still holds the previous request.

## Exit code and stdout

A plain `reset`, a `reset --no-test` with no overlay, and `reset --clear-refs` print nothing on success and exit 0.

Every `reset` that passes `--ref` or `--load` prints exactly one JSON document on stdout, on success and on failure.

Exit 0 when the load succeeded and tests were skipped or every test passed:

```json
{
  "slot": 1,
  "loaded": true,
  "origin": {
    "source": "snapshots/current",
    "snapshot": "2026-11-04",
    "builtAt": "2026-11-04T09:00:00",
    "refs": [
      {
        "repository": "/home/me/git/RepoA",
        "baseline": "RepoA",
        "ref": "feature/xxx",
        "sha": "abcdef"
      }
    ]
  },
  "savedRefs": [
    {"repository": "/home/me/git/RepoA", "ref": "feature/xxx"}
  ],
  "tests": {
    "run": 120,
    "passed": 120,
    "failures": [],
    "errors": []
  }
}
```

`--no-test` uses `"tests": null`. An empty `failures` and an empty `errors` is success even when `run` is 0.

A failed test suite prints the same shape, exits 1, and writes `pds: <count> of <run> tests failed` to stderr. `<count>` is the number of `failures` plus the number of `errors`. The image and `tests.json` remain.

A fetch failure, an archive failure, a missing manifest SHA, a missing `snapshots/current`, a busy build port, or a Pharo run that exits without writing the results file leaves the image and `refs.json` unreplaced. Print this JSON, exit 1, and write the same `error` to stderr as `pds: ...`:

```json
{"slot": 1, "loaded": false, "error": "RepoA: git fetch origin feature/xxx failed: ..."}
```

## Package structure changes

The limit is the incremental `build-snapshot` limit. Changed methods, and packages or dependencies added by the baseline, are loaded. Removed or renamed packages and classes stay in the image. The test list is built from the branch's `srcDir`, so a package removed on the branch is not run. Rebuild the snapshot with `build-snapshot --full` for that branch. This command does not merge `st-projects.json` with another file and rebuild the slot from dev-base.

## Files

- `pds/cli.py`: the options above, and the overlay exit code.
- `pds/slot.py`: the overlay, keeping and deleting `refs.json`, `origin.refs`, `tests.json`, and `savedRefs` plus `tests` on status.
- `pds/sources.py`: use the existing `fetch_branch_sha` and `extract_src_dir` for the requested branch.
- `pds/st/load_baselines.st` and `pds/st/run_tests.st`: reuse the current templates with the selected repositories and the package list.
- `README.md` and `skills/pharo-dev-spaces/SKILL.md`: the overlay command, `refs.json`, the new status fields, and the removal/rename limit.
- Unit tests cover flag combinations, `NAME` resolution, keeping and replacing `refs.json`, a failed load leaving the previous image, a failed suite leaving the new image and exiting 1, and the load script omitting repositories that were not named.

## Out of scope

- Running tests from `up` or `gui`.
- Loading a local branch, an unpushed commit, or uncommitted working-tree changes.
- Passing a SHA as a ref.
- Reloading unnamed repositories at the current `origin/<branch>`.
- Discarding the slot image when tests fail, the way a snapshot build leaves `snapshots/current` unchanged.
