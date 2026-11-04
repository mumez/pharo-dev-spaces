import json
import os

import pytest

from pds import cli, slot
from pds.cli import build_parser
from pds.pharo import PharoRunError, PortInUseError
from pds.slot import parse_ref_spec, resolve_project, resolve_ref_specs, slot_dir, validate_saved_refs
from tests.test_image_dir import make_image_dir
from tests.test_sources import cloned_repository_on, git

REPO_A = {"repository": "/home/me/git/RepoA", "baseline": "RepoA", "srcDir": "src", "groups": ["default"]}
REPO_B = {"repository": "/home/me/git/RepoB", "baseline": "RepoB", "srcDir": "src", "groups": ["default"]}
PROJECTS = [REPO_A, REPO_B]


def test_ref_spec_splits_on_the_first_colon_and_strips_origin_prefix():
    assert parse_ref_spec("RepoA:feature/xxx") == ("RepoA", "feature/xxx")
    assert parse_ref_spec("RepoA:origin/feature/xxx") == ("RepoA", "feature/xxx")
    assert parse_ref_spec("RepoA:feature:xxx") == ("RepoA", "feature:xxx")


@pytest.mark.parametrize("spec", ["RepoA", "RepoA:", ":feature", "RepoA:origin/", ""])
def test_ref_spec_requires_a_name_and_a_branch(spec):
    with pytest.raises(ValueError, match="NAME:BRANCH"):
        parse_ref_spec(spec)


def test_name_matches_baseline_before_directory_or_path():
    other = {"repository": "/elsewhere/RepoA", "baseline": "Other", "srcDir": "src", "groups": ["default"]}

    assert resolve_project([REPO_A, other], "RepoA") == REPO_A


def test_name_matches_repository_directory_when_baseline_does_not():
    project = {"repository": "/home/me/git/repo-b", "baseline": "BaselineB", "srcDir": "src", "groups": ["default"]}

    assert resolve_project([project], "repo-b") == project


def test_name_matches_absolute_repository_path_last():
    assert resolve_project(PROJECTS, "/home/me/git/RepoA") == REPO_A


def test_name_with_no_match_is_rejected():
    with pytest.raises(ValueError, match="no project"):
        resolve_project(PROJECTS, "Missing")


def test_name_with_several_matches_is_rejected_without_falling_through():
    shared = [
        {"repository": "/git/one/Shared", "baseline": "Shared", "srcDir": "src", "groups": ["default"]},
        {"repository": "/git/two/Shared", "baseline": "Shared", "srcDir": "src", "groups": ["default"]},
    ]

    with pytest.raises(ValueError, match="more than one"):
        resolve_project(shared, "Shared")


def test_ref_specs_reject_the_same_repository_twice():
    with pytest.raises(ValueError, match="given twice"):
        resolve_ref_specs(PROJECTS, ["RepoA:feature/one", "/home/me/git/RepoA:feature/two"])


def test_saved_refs_keep_repository_and_branch_without_origin_prefix():
    entries = [{"repository": REPO_A["repository"], "ref": "origin/feature/xxx"}]

    assert validate_saved_refs(entries, PROJECTS, "refs.json") == [
        {"repository": REPO_A["repository"], "ref": "feature/xxx"}
    ]


def test_saved_refs_reject_a_non_list():
    with pytest.raises(TypeError):
        validate_saved_refs({"repository": REPO_A["repository"], "ref": "feature/xxx"}, PROJECTS, "refs.json")


@pytest.mark.parametrize(
    "entries",
    [
        [{"repository": REPO_A["repository"], "ref": "feature/xxx", "sha": "abc"}],
        [{"repository": REPO_A["repository"]}],
        [{"repository": "/missing", "ref": "feature/xxx"}],
        [
            {"repository": REPO_A["repository"], "ref": "feature/one"},
            {"repository": REPO_A["repository"], "ref": "feature/two"},
        ],
        [{"repository": REPO_A["repository"], "ref": "origin/"}],
    ],
)
def test_saved_refs_reject_a_schema_mismatch(entries):
    with pytest.raises(ValueError):
        validate_saved_refs(entries, PROJECTS, "refs.json")


def test_saved_refs_error_names_an_unknown_repository():
    with pytest.raises(ValueError, match="not in st-projects.json"):
        validate_saved_refs([{"repository": "/missing", "ref": "feature/xxx"}], PROJECTS, "refs.json")


def test_omitted_test_flag_is_distinct_from_explicit_test():
    omitted = build_parser().parse_args(["slot", "1", "reset"])
    explicit = build_parser().parse_args(["slot", "1", "reset", "--test"])
    skipped = build_parser().parse_args(["slot", "1", "reset", "--no-test"])

    assert omitted.test is None
    assert explicit.test is True
    assert skipped.test is False
    assert build_parser().parse_args(
        ["slot", "1", "reset", "--ref", "RepoA:feature/xxx", "--ref", "RepoB:feature/yyy"]
    ).ref == ["RepoA:feature/xxx", "RepoB:feature/yyy"]


def run_reset(layout, monkeypatch, capsys, *argv):
    monkeypatch.setattr(cli.Layout, "default", classmethod(lambda cls: layout))
    exit_code = cli.main(["slot", "1", "reset", *argv])
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def write_slot_image(layout, contents="dirty"):
    make_image_dir(layout.plain_dir)
    image_dir = make_image_dir(slot_dir(layout, 1))
    (image_dir / "Pharo.image").write_text(contents)
    return image_dir


def test_usage_errors_print_no_json_and_leave_the_slot_unchanged(layout, monkeypatch, capsys):
    image_dir = write_slot_image(layout)
    saved = [{"repository": REPO_A["repository"], "ref": "feature/xxx", "sha": "nope"}]
    (image_dir / "refs.json").write_text(json.dumps(saved))
    layout.projects_file.write_text(json.dumps(PROJECTS))

    for argv in (
        ["--test"],
        ["--clear-refs", "--ref", "RepoA:feature/xxx"],
        ["--clear-refs", "--load"],
        ["--ref", "Nope:feature/xxx"],
        ["--ref", "RepoA"],
        ["--load"],
    ):
        exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, *argv)

        assert exit_code == 1
        assert stdout == ""
        assert stderr.startswith("pds: ")
        assert (image_dir / "Pharo.image").read_text() == "dirty"
        assert json.loads((image_dir / "refs.json").read_text()) == saved


def test_load_without_refs_file_is_rejected(layout, monkeypatch, capsys):
    image_dir = write_slot_image(layout)
    layout.projects_file.write_text(json.dumps(PROJECTS))

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--load")

    assert exit_code == 1
    assert stdout == ""
    assert "refs.json" in stderr
    assert (image_dir / "Pharo.image").read_text() == "dirty"
    assert not (image_dir / "refs.json").exists()


def test_plain_reset_keeps_refs_and_drops_slot_tests(layout, monkeypatch, capsys):
    make_image_dir(layout.dev_base_dir)
    image_dir = write_slot_image(layout)
    saved = [{"repository": REPO_A["repository"], "ref": "feature/xxx"}]
    (image_dir / "refs.json").write_text(json.dumps(saved))
    (image_dir / "tests.json").write_text('{"run": 1, "passed": 0, "failures": ["x"], "errors": []}')

    for argv in ([], ["--no-test"]):
        exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, *argv)

        assert (exit_code, stdout, stderr) == (0, "", "")
        assert json.loads((image_dir / "refs.json").read_text()) == saved
        assert not (image_dir / "tests.json").exists()
        assert "refs" not in json.loads((image_dir / "origin.json").read_text())


def test_clear_refs_drops_refs_only_after_the_new_image_is_in_place(layout, monkeypatch, capsys):
    make_image_dir(layout.dev_base_dir)
    image_dir = write_slot_image(layout, "dirty")
    (image_dir / "refs.json").write_text("[]")
    (image_dir / "ports.json").write_text('{"sis": 8187}')

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--clear-refs")

    assert (exit_code, stdout, stderr) == (0, "", "")
    assert (image_dir / "Pharo.image").read_text() == "image"
    assert not (image_dir / "refs.json").exists()
    assert json.loads((image_dir / "ports.json").read_text()) == {"sis": 8187}


def test_clear_refs_succeeds_when_refs_file_is_already_absent(layout, monkeypatch, capsys):
    make_image_dir(layout.dev_base_dir)
    write_slot_image(layout)

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--clear-refs")

    assert (exit_code, stdout, stderr) == (0, "", "")


def test_failed_clear_refs_leaves_the_saved_refs(layout, monkeypatch, capsys):
    image_dir = write_slot_image(layout)
    (image_dir / "refs.json").write_text("[]")

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--clear-refs")

    assert exit_code == 1
    assert stdout == ""
    assert stderr.startswith("pds: ")
    assert (image_dir / "refs.json").read_text() == "[]"
    assert (image_dir / "Pharo.image").read_text() == "dirty"


def project_entry(repository, baseline):
    return {"repository": str(repository), "baseline": baseline, "srcDir": "src", "groups": ["default"]}


def write_snapshot(layout, image_text="snapshot", built_at="2026-11-04T09:00:00", repositories=()):
    make_image_dir(layout.current_snapshot_dir)
    (layout.current_snapshot_dir / "Pharo.image").write_text(image_text)
    manifest = {"builtAt": built_at, "repositories": list(repositories)}
    (layout.snapshots_dir / "2026-11-04.json").write_text(json.dumps(manifest))


def record_pharo(monkeypatch, runs):
    def run(layout, image, script, port, timeout, save=False):
        runs.append({"script": script.read_text(), "port": port, "timeout": timeout, "save": save})
        (image.parent / "pharo-local" / "iceberg").mkdir(parents=True)

    monkeypatch.setattr(slot, "run_pharo", run)


def test_overlay_loads_only_the_named_repository_and_records_the_fetched_sha(layout, monkeypatch, capsys, tmp_path):
    cloned = cloned_repository_on(tmp_path, "feature/xxx")
    projects = [project_entry(cloned["clone"], "RepoA"), project_entry("/missing/RepoB", "RepoB")]
    layout.projects_file.write_text(json.dumps(projects))
    write_snapshot(layout)
    image_dir = write_slot_image(layout, "old")
    (image_dir / "refs.json").write_text(json.dumps([{"repository": "/missing/RepoB", "ref": "old"}]))
    runs = []
    record_pharo(monkeypatch, runs)

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--ref", "RepoA:origin/feature/xxx", "--no-test")

    assert exit_code == 0
    assert stderr == ""
    result = json.loads(stdout)
    assert result["loaded"] is True
    assert result["tests"] is None
    assert result["origin"]["refs"] == [
        {
            "repository": str(cloned["clone"]),
            "baseline": "RepoA",
            "ref": "feature/xxx",
            "sha": cloned["latest_sha"],
        }
    ]
    assert result["savedRefs"] == [{"repository": str(cloned["clone"]), "ref": "feature/xxx"}]
    assert result["origin"]["snapshot"] == "2026-11-04"
    assert "RepoA" in runs[0]["script"]
    assert "RepoB" not in runs[0]["script"]
    assert runs[0]["port"] == 8096
    assert runs[0]["timeout"] == 3600
    assert runs[0]["save"] is True
    assert (image_dir / "Pharo.image").read_text() == "snapshot"
    assert not (image_dir / "pharo-local" / "iceberg").exists()
    assert not (image_dir / "tests.json").exists()
    assert not list(image_dir.glob("*.st"))
    assert git_head(cloned["clone"]) != cloned["latest_sha"]


def test_ref_with_load_replaces_the_saved_refs(layout, monkeypatch, capsys, tmp_path):
    cloned = cloned_repository_on(tmp_path, "feature/xxx")
    layout.projects_file.write_text(json.dumps([project_entry(cloned["clone"], "RepoA"), REPO_B]))
    write_snapshot(layout)
    image_dir = write_slot_image(layout)
    (image_dir / "refs.json").write_text(json.dumps([{"repository": REPO_B["repository"], "ref": "feature/yyy"}]))
    record_pharo(monkeypatch, [])

    exit_code, stdout, stderr = run_reset(
        layout, monkeypatch, capsys, "--ref", "RepoA:feature/xxx", "--load", "--no-test"
    )

    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout)["savedRefs"] == [{"repository": str(cloned["clone"]), "ref": "feature/xxx"}]


def test_load_fetches_again_and_leaves_the_refs_file_unchanged(layout, monkeypatch, capsys, tmp_path):
    cloned = cloned_repository_on(tmp_path, "feature/xxx")
    repository = str(cloned["clone"])
    layout.projects_file.write_text(json.dumps([project_entry(repository, "RepoA")]))
    write_snapshot(layout)
    image_dir = write_slot_image(layout)
    refs_text = f'[{{"repository": "{repository}", "ref": "origin/feature/xxx"}}]'
    (image_dir / "refs.json").write_text(refs_text)
    record_pharo(monkeypatch, [])

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--load", "--no-test")

    assert exit_code == 0
    assert stderr == ""
    assert (image_dir / "refs.json").read_text() == refs_text
    assert json.loads(stdout)["origin"]["refs"][0]["ref"] == "feature/xxx"
    assert json.loads(stdout)["origin"]["refs"][0]["sha"] == cloned["latest_sha"]


def test_failed_fetch_leaves_the_image_and_refs_and_prints_loaded_false(layout, monkeypatch, capsys, tmp_path):
    cloned = cloned_repository_on(tmp_path, "develop")
    layout.projects_file.write_text(json.dumps([project_entry(cloned["clone"], "RepoA")]))
    write_snapshot(layout)
    image_dir = write_slot_image(layout, "old")
    saved = [{"repository": str(cloned["clone"]), "ref": "develop"}]
    (image_dir / "refs.json").write_text(json.dumps(saved))

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--ref", "RepoA:feature/xxx", "--no-test")

    payload = json.loads(stdout)
    assert exit_code == 1
    assert payload == {"slot": 1, "loaded": False, "error": payload["error"]}
    assert "feature/xxx" in payload["error"]
    assert stderr == f"pds: {payload['error']}\n"
    assert (image_dir / "Pharo.image").read_text() == "old"
    assert json.loads((image_dir / "refs.json").read_text()) == saved


def test_overlay_requires_snapshots_current_and_plain_reset_still_uses_dev_base(layout, monkeypatch, capsys, tmp_path):
    cloned = cloned_repository_on(tmp_path, "feature/xxx")
    layout.projects_file.write_text(json.dumps([project_entry(cloned["clone"], "RepoA")]))
    make_image_dir(layout.dev_base_dir)
    image_dir = write_slot_image(layout, "old")
    saved = [{"repository": str(cloned["clone"]), "ref": "develop"}]
    (image_dir / "refs.json").write_text(json.dumps(saved))

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--ref", "RepoA:feature/xxx", "--no-test")

    payload = json.loads(stdout)
    assert exit_code == 1
    assert payload["loaded"] is False
    assert "build-snapshot --full" in payload["error"]
    assert stderr == f"pds: {payload['error']}\n"
    assert (image_dir / "Pharo.image").read_text() == "old"
    assert json.loads((image_dir / "refs.json").read_text()) == saved

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys)
    assert (exit_code, stdout, stderr) == (0, "", "")
    assert json.loads((image_dir / "origin.json").read_text())["source"] == "dev-base"


def test_busy_build_port_does_not_replace_the_image(layout, monkeypatch, capsys, tmp_path):
    cloned = cloned_repository_on(tmp_path, "feature/xxx")
    layout.projects_file.write_text(json.dumps([project_entry(cloned["clone"], "RepoA")]))
    write_snapshot(layout)
    image_dir = write_slot_image(layout, "old")

    def port_in_use(environment):
        raise PortInUseError("SIS port 8096 is already in use by another process")

    monkeypatch.setattr(slot, "ensure_pharo_ports_available", port_in_use)

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--ref", "RepoA:feature/xxx", "--no-test")

    payload = json.loads(stdout)
    assert exit_code == 1
    assert payload["loaded"] is False
    assert "8096" in payload["error"]
    assert stderr == f"pds: {payload['error']}\n"
    assert (image_dir / "Pharo.image").read_text() == "old"


def test_pharo_failure_does_not_replace_the_image(layout, monkeypatch, capsys, tmp_path):
    cloned = cloned_repository_on(tmp_path, "feature/xxx")
    layout.projects_file.write_text(json.dumps([project_entry(cloned["clone"], "RepoA")]))
    write_snapshot(layout)
    image_dir = write_slot_image(layout, "old")
    (image_dir / "refs.json").write_text("[]")

    def fail(layout, image, script, port, timeout, save=False):
        raise PharoRunError("overlay.st failed with exit code 1")

    monkeypatch.setattr(slot, "run_pharo", fail)

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--ref", "RepoA:feature/xxx", "--no-test")

    payload = json.loads(stdout)
    assert exit_code == 1
    assert payload["loaded"] is False
    assert stderr == f"pds: {payload['error']}\n"
    assert (image_dir / "Pharo.image").read_text() == "old"
    assert (image_dir / "refs.json").read_text() == "[]"


def add_package(repository, name):
    directory = repository / "src" / name
    directory.mkdir(parents=True)
    (directory / "package.st").write_text(f"Package {{ #name : '{name}' }}\n")
    git("add", ".", cwd=repository)
    git("commit", "-q", "-m", name, cwd=repository)
    git("push", "-q", "origin", "HEAD", cwd=repository)


def test_overlay_tests_packages_from_the_fetched_branch_and_the_manifest_sha(layout, monkeypatch, capsys, tmp_path):
    (tmp_path / "overlaid").mkdir()
    (tmp_path / "other").mkdir()
    overlaid = cloned_repository_on(tmp_path / "overlaid", "feature/xxx")
    other = cloned_repository_on(tmp_path / "other", "develop")
    author = tmp_path / "overlaid" / "author"
    add_package(author, "BaselineOfRepoA")
    add_package(author, ".hidden")
    add_package(author, "Visible")
    manifest_sha = git("rev-parse", "HEAD", cwd=other["clone"])
    add_package(tmp_path / "other" / "author", "NewPkg")
    projects = [project_entry(overlaid["clone"], "RepoA"), project_entry(other["clone"], "RepoB")]
    layout.projects_file.write_text(json.dumps(projects))
    write_snapshot(layout, repositories=[{"repository": str(other["clone"]), "baseline": "RepoB", "sha": manifest_sha}])
    write_slot_image(layout, "old")
    runs = []
    passed = {"run": 1, "passed": 1, "failures": [], "errors": []}

    def run(layout, image, script, port, timeout, save=False):
        runs.append(script.read_text())
        (image.parent / "test-results.json").write_text(json.dumps(passed))

    monkeypatch.setattr(slot, "run_pharo", run)

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--ref", "RepoA:feature/xxx")

    assert (exit_code, stderr) == (0, "")
    script = runs[0]
    assert "#( 'Pkg' 'Visible' 'Pkg' ) do:" in script
    assert "NewPkg" not in script
    assert "BaselineOfRepoA" not in script
    assert ".hidden" not in script
    assert "'RepoB'" not in script
    result = json.loads(stdout)
    assert result["tests"] == passed
    assert result["loaded"] is True
    slot_directory = slot_dir(layout, 1)
    assert json.loads((slot_directory / "tests.json").read_text()) == passed
    assert not (slot_directory / "test-results.json").exists()


def test_explicit_test_flag_runs_tests(layout, monkeypatch, capsys, tmp_path):
    cloned = cloned_repository_on(tmp_path, "feature/xxx")
    layout.projects_file.write_text(json.dumps([project_entry(cloned["clone"], "RepoA")]))
    write_snapshot(layout)
    write_slot_image(layout)
    none_run = {"run": 0, "passed": 0, "failures": [], "errors": []}

    def run(layout, image, script, port, timeout, save=False):
        (image.parent / "test-results.json").write_text(json.dumps(none_run))

    monkeypatch.setattr(slot, "run_pharo", run)

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--ref", "RepoA:feature/xxx", "--test")

    assert (exit_code, stderr) == (0, "")
    assert json.loads(stdout)["tests"] == none_run


def test_failed_suite_keeps_the_loaded_image_and_exits_1(layout, monkeypatch, capsys, tmp_path):
    cloned = cloned_repository_on(tmp_path, "feature/xxx")
    repository = str(cloned["clone"])
    layout.projects_file.write_text(json.dumps([project_entry(repository, "RepoA")]))
    write_snapshot(layout)
    image_dir = write_slot_image(layout, "old")
    (image_dir / "refs.json").write_text(json.dumps([{"repository": repository, "ref": "develop"}]))
    failed = {"run": 3, "passed": 1, "failures": ["ATest>>#testA"], "errors": ["ATest>>#testB"]}

    def run(layout, image, script, port, timeout, save=False):
        image.write_text("loaded")
        (image.parent / "test-results.json").write_text(json.dumps(failed))

    monkeypatch.setattr(slot, "run_pharo", run)

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--ref", "RepoA:feature/xxx")

    result = json.loads(stdout)
    assert exit_code == 1
    assert stderr == "pds: 2 of 3 tests failed\n"
    assert result["loaded"] is True
    assert result["tests"] == failed
    assert (image_dir / "Pharo.image").read_text() == "loaded"
    assert json.loads((image_dir / "tests.json").read_text()) == failed
    assert json.loads((image_dir / "refs.json").read_text()) == [{"repository": repository, "ref": "feature/xxx"}]
    assert not (image_dir / "test-results.json").exists()


def test_missing_test_results_do_not_replace_the_image(layout, monkeypatch, capsys, tmp_path):
    cloned = cloned_repository_on(tmp_path, "feature/xxx")
    layout.projects_file.write_text(json.dumps([project_entry(cloned["clone"], "RepoA")]))
    write_snapshot(layout)
    image_dir = write_slot_image(layout, "old")
    (image_dir / "refs.json").write_text("[]")
    record_pharo(monkeypatch, [])

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--ref", "RepoA:feature/xxx")

    payload = json.loads(stdout)
    assert exit_code == 1
    assert payload["loaded"] is False
    assert stderr == f"pds: {payload['error']}\n"
    assert (image_dir / "Pharo.image").read_text() == "old"
    assert (image_dir / "refs.json").read_text() == "[]"


@pytest.mark.parametrize(
    "repositories",
    [
        [],
        [{"repository": "filled-below", "baseline": "RepoB"}],
        [{"repository": "filled-below", "baseline": "RepoB", "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}],
    ],
)
def test_unusable_manifest_sha_does_not_replace_the_image(layout, monkeypatch, capsys, tmp_path, repositories):
    (tmp_path / "overlaid").mkdir()
    (tmp_path / "other").mkdir()
    overlaid = cloned_repository_on(tmp_path / "overlaid", "feature/xxx")
    other = cloned_repository_on(tmp_path / "other", "develop")
    if repositories:
        repositories[0]["repository"] = str(other["clone"])
    projects = [project_entry(overlaid["clone"], "RepoA"), project_entry(other["clone"], "RepoB")]
    layout.projects_file.write_text(json.dumps(projects))
    write_snapshot(layout, repositories=repositories)
    image_dir = write_slot_image(layout, "old")
    saved = [{"repository": str(overlaid["clone"]), "ref": "develop"}]
    (image_dir / "refs.json").write_text(json.dumps(saved))

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--ref", "RepoA:feature/xxx")

    payload = json.loads(stdout)
    assert exit_code == 1
    assert payload["loaded"] is False
    assert "RepoB" in payload["error"]
    assert stderr == f"pds: {payload['error']}\n"
    assert (image_dir / "Pharo.image").read_text() == "old"
    assert json.loads((image_dir / "refs.json").read_text()) == saved


def git_head(repository):
    import subprocess

    return subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def test_running_slot_is_rejected_before_an_overlay(layout, monkeypatch, capsys):
    image_dir = write_slot_image(layout)
    (image_dir / "pharo.pid").write_text(str(os.getpid()))
    layout.projects_file.write_text(json.dumps(PROJECTS))

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--ref", "RepoA:feature/xxx")

    assert exit_code == 1
    assert stdout == ""
    assert "pds slot 1 down" in stderr
    assert (image_dir / "Pharo.image").read_text() == "dirty"
