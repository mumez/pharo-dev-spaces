import json
import os

import pytest

from pds import cli
from pds.cli import build_parser
from pds.slot import parse_ref_spec, resolve_project, resolve_ref_specs, slot_dir, validate_saved_refs
from tests.test_image_dir import make_image_dir

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


@pytest.mark.parametrize(
    "entries",
    [
        {"repository": REPO_A["repository"], "ref": "feature/xxx"},
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


def test_running_slot_is_rejected_before_an_overlay(layout, monkeypatch, capsys):
    image_dir = write_slot_image(layout)
    (image_dir / "pharo.pid").write_text(str(os.getpid()))
    layout.projects_file.write_text(json.dumps(PROJECTS))

    exit_code, stdout, stderr = run_reset(layout, monkeypatch, capsys, "--ref", "RepoA:feature/xxx")

    assert exit_code == 1
    assert stdout == ""
    assert "pds slot 1 down" in stderr
    assert (image_dir / "Pharo.image").read_text() == "dirty"
