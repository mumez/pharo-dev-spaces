from pathlib import Path

import pytest

from pds.baseline import BaselineSpec, project_entry

SAMPLE_REPOSITORY = Path(__file__).parent / "fixtures" / "sample-repo"


@pytest.fixture
def sample_spec():
    return BaselineSpec.from_repository(SAMPLE_REPOSITORY)


def test_reads_baseline_name_and_src_dir_of_repository(sample_spec):
    assert sample_spec.name == "Sample"
    assert sample_spec.src_dir == "src"


def test_collects_packages_from_all_baseline_methods(sample_spec):
    assert set(sample_spec.package_requirements) == {"Sample-Model", "Sample-Core", "Sample-Tests", "Sample-Extra"}


def test_load_order_puts_required_packages_first(sample_spec):
    order = sample_spec.load_order(["default"])

    assert order == ["BaselineOfSample", "Sample-Core", "Sample-Model", "Sample-Tests"]


def test_group_requirements_are_expanded_to_their_packages(sample_spec):
    order = sample_spec.load_order(["Tests"])

    assert order == ["BaselineOfSample", "Sample-Core", "Sample-Model", "Sample-Tests"]


def test_packages_outside_requested_groups_are_excluded(sample_spec):
    assert "Sample-Extra" not in sample_spec.load_order(["default"])
    assert sample_spec.load_order(["Extra"]) == ["BaselineOfSample", "Sample-Core", "Sample-Extra"]


def test_without_default_group_all_packages_are_loaded():
    spec = BaselineSpec("X", "src", {"X-A": ["X-B"], "X-B": []}, groups={})

    assert spec.load_order(["default"]) == ["BaselineOfX", "X-B", "X-A"]


def test_cyclic_requirements_are_rejected():
    spec = BaselineSpec("X", "src", {"X-A": ["X-B"], "X-B": ["X-A"]}, groups={})

    with pytest.raises(ValueError, match="cycl"):
        spec.load_order(["default"])


def test_project_entry_describes_repository_for_projects_json():
    entry = project_entry(SAMPLE_REPOSITORY)

    assert entry == {
        "repository": str(SAMPLE_REPOSITORY.resolve()),
        "baseline": "Sample",
        "srcDir": "src",
        "groups": ["default"],
        "packages": ["BaselineOfSample", "Sample-Core", "Sample-Model", "Sample-Tests"],
    }
