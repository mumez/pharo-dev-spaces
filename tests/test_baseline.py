from pathlib import Path

import pytest

from pds.baseline import project_entry

SAMPLE_REPOSITORY = Path(__file__).parent / "fixtures" / "sample-repo"


def test_project_entry_describes_repository_for_st_projects_json():
    entry = project_entry(SAMPLE_REPOSITORY)

    assert entry == {
        "repository": str(SAMPLE_REPOSITORY.resolve()),
        "baseline": "Sample",
        "srcDir": "src",
        "groups": ["default"],
    }


def test_project_entry_keeps_requested_groups():
    assert project_entry(SAMPLE_REPOSITORY, ["Core", "Tests"])["groups"] == ["Core", "Tests"]


def test_src_dir_defaults_to_src_without_project_file(tmp_path):
    (tmp_path / "src" / "BaselineOfX").mkdir(parents=True)

    assert project_entry(tmp_path)["srcDir"] == "src"


def test_missing_repository_is_reported_as_such(tmp_path):
    with pytest.raises(FileNotFoundError, match=r"repository .*/missing does not exist"):
        project_entry(tmp_path / "missing")


def test_repository_without_baseline_is_rejected(tmp_path):
    (tmp_path / "src").mkdir()

    with pytest.raises(FileNotFoundError, match="no BaselineOf"):
        project_entry(tmp_path)
