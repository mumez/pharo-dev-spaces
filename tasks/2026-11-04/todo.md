# TODO: Overlay a remote branch onto a slot

Design: `tasks/2026-11-04/plan.md`.

- Unit tests: `uv run pytest`
- Do not launch Pharo. Stub `run_pharo` the way `tests/test_snapshot.py` does.

---

## Task 1: Status reports `savedRefs` and `tests`

**Description:** `pds slot N status` and `pds list-slots` always include `savedRefs` (`refs.json`, or `[]`) and `tests` (`tests.json`, or `null`). A plain reset still writes `origin.json` with no `refs` key.

**Acceptance criteria:**
- [ ] A slot with both files reports them
- [ ] A slot without them reports `savedRefs: []` and `tests: null`
- [ ] Existing full-dict status assertions include the new keys

**Verification:**
- [ ] `uv run pytest tests/test_slot.py`

**Dependencies:** none

**Files:** `pds/slot.py`, `tests/test_slot.py`

---

## Task 2: Resolve `NAME:BRANCH` and validate `refs.json`

**Description:** Split a spec on the first colon, strip a leading `origin/`, and resolve `NAME` in order: baseline, repository directory name, absolute path. Stop at the first unique match. Reject zero matches, several matches, a duplicate repository, and a `refs.json` entry that is not exactly `{repository, ref}` or whose repository is not in `st-projects.json`.

**Acceptance criteria:**
- [ ] `RepoA`, the directory name, and the absolute path each select one project
- [ ] `origin/feature/xxx` is `feature/xxx`
- [ ] Ambiguous names, empty sides, duplicates, unknown keys, and unknown repositories are rejected before any image work

**Verification:**
- [ ] `uv run pytest tests/test_slot_overlay.py`

**Dependencies:** none

**Files:** `pds/slot.py`, `tests/test_slot_overlay.py`

---

## Task 3: Reset flags and usage errors

**Description:** Add `--ref` (repeatable), `--load`, `--test` / `--no-test` (`BooleanOptionalAction`, default `None`), and `--clear-refs` to `pds slot N reset`. Usage errors print `pds: ...` on stderr, print no JSON, and leave the image and `refs.json` unchanged.

**Acceptance criteria:**
- [ ] Omitted `--test` is distinct from `--test`
- [ ] `--test` without an overlay, `--clear-refs` with `--ref` or `--load`, `--load` with no `refs.json`, a bad spec, and a running slot are rejected
- [ ] A running slot uses the current message that tells the user to run `down`

**Verification:**
- [ ] `uv run pytest tests/test_cli.py tests/test_slot_overlay.py`

**Dependencies:** Task 2

**Files:** `pds/cli.py`, `pds/slot.py`, `tests/test_cli.py`, `tests/test_slot_overlay.py`

---

## Task 4: Keep `refs.json` across reset, and `--clear-refs`

**Description:** `refs.json` survives reset the way `ports.json` does. `--clear-refs` recreates a clean copy (snapshot, or dev-base when no snapshot exists) and leaves `refs.json` out. Success when the file was already absent. A failed replacement leaves the old file in place.

**Acceptance criteria:**
- [ ] Plain `reset` and `reset --no-test` keep `refs.json`, run no tests, and print nothing
- [ ] `--clear-refs` deletes `refs.json` only after the new image is in place
- [ ] `--clear-refs` prints nothing and exits 0

**Verification:**
- [ ] `uv run pytest tests/test_slot.py tests/test_slot_overlay.py tests/test_cli.py`

**Dependencies:** Task 3

**Files:** `pds/slot.py`, `pds/cli.py`, `tests/test_slot_overlay.py`

---

## Task 5: Overlay the named repositories

**Description:** `--ref` and `--load` copy `snapshots/current` only, `git fetch` each named branch, and Metacello-load only those repositories. Unnamed repositories stay as they are in the snapshot. One Pharo run, build port 8096, timeout 3600s. Save when the script exits. Promote only after the script exits, with the Iceberg cache removed. `--ref` replaces `refs.json` after a successful load. `--load` fetches again and leaves the file bytes unchanged. `--ref` together with `--load` uses the `--ref` set. Fetch, archive, missing snapshot, and a busy build port leave the image and `refs.json` unreplaced and print `{"slot", "loaded": false, "error"}`.

**Acceptance criteria:**
- [ ] The load script names only the overlaid repositories
- [ ] `origin.refs` records repository, baseline, ref (no `origin/` prefix), and the fetched sha
- [ ] A failed load keeps the previous image and the previous `refs.json`
- [ ] Missing `snapshots/current` tells the user to run `pds build-snapshot --full`. A plain reset still falls back to dev-base

**Verification:**
- [ ] `uv run pytest tests/test_slot_overlay.py`

**Dependencies:** Task 4

**Files:** `pds/slot.py`, `pds/cli.py`, `tests/test_slot_overlay.py`

---

## Task 6: Run the project tests unless `--no-test`

**Description:** An overlay runs tests unless `--no-test`. Package names come from the fetched `srcDir` for overlaid repositories and from `git archive` of the manifest sha for the others. Skip `BaselineOf*` and dot-directories. A missing sha, missing git object, or a repository absent from the manifest fails without replacing the image. Write `tests.json` (not kept across reset) and delete Pharo's temporary results file. A failed suite still promotes the image and `refs.json`, prints the success JSON shape, exits 1, and writes `pds: <failures+errors> of <run> tests failed`. Empty failure and error arrays succeed even when `run` is 0. `--no-test` sends `"tests": null` and does not create `tests.json`. A Pharo exit without a results file does not replace the image.

**Acceptance criteria:**
- [ ] Default and explicit `--test` both run tests
- [ ] The package list omits unnamed repositories' freshly fetched branches and uses the manifest sha
- [ ] A failed suite leaves the new image and exits 1
- [ ] A missing results file leaves the previous image

**Verification:**
- [ ] `uv run pytest`

**Dependencies:** Task 5

**Files:** `pds/slot.py`, `pds/cli.py`, `tests/test_slot_overlay.py`

---

## Task 7: Document the command

**Description:** Update `README.md` and `skills/pharo-dev-spaces/SKILL.md` with the overlay command, `refs.json`, `savedRefs` and `tests`, and the same removal/rename limit as an incremental snapshot. A failed suite keeps the slot image. An overlay is a review image: do not reset it away just because a newer snapshot exists, unless the user asked.

**Acceptance criteria:**
- [ ] README shows `--ref`, `--load`, `--no-test`, and `--clear-refs`
- [ ] The skill can choose this command when the user wants to review a remote branch

**Verification:**
- [ ] `uv run pytest`
- [ ] `uv run ruff check pds tests`

**Dependencies:** Task 6

**Files:** `README.md`, `skills/pharo-dev-spaces/SKILL.md`
