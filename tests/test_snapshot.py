import json
import tarfile
from datetime import date
from pathlib import Path

import pytest

from pds import snapshot
from pds.image_dir import image_path
from pds.snapshot import SnapshotBuildError, build_snapshot
from pds.sources import FetchedSource
from tests.test_image_dir import make_image_dir

BUILD_DATE = date(2026, 10, 13)
PROJECT = {
    "repository": "/repos/Historia",
    "baseline": "Historia",
    "srcDir": "src",
    "groups": ["default"],
    "packages": ["BaselineOfHistoria", "Historia-Core", "Historia-Tests"],
}


@pytest.fixture
def build_layout(layout, monkeypatch):
    make_image_dir(layout.plain_dir)
    make_image_dir(layout.dev_base_dir)
    layout.projects_file.write_text(json.dumps([PROJECT]))
    monkeypatch.setattr(
        snapshot,
        "fetch_project_sources",
        lambda projects, extract_root: [FetchedSource(PROJECT, "abc123", Path(extract_root) / "Historia" / "src")],
    )
    return layout


def fake_pharo_run(test_results, scripts=None):
    def run(layout, image, script, port, timeout, save=False):
        if scripts is not None:
            scripts.append(script.read_text())
        (image.parent / "pharo-local" / "iceberg").mkdir(parents=True, exist_ok=True)
        (image.parent / snapshot.TEST_RESULTS_FILE_NAME).write_text(json.dumps(test_results))

    return run


PASSED = {"run": 2, "passed": 2, "failures": [], "errors": []}


def test_full_build_loads_baselines_with_metacello_and_tests_loaded_packages(build_layout, monkeypatch):
    scripts = []
    monkeypatch.setattr(snapshot, "run_pharo", fake_pharo_run(PASSED, scripts))

    build_snapshot(build_layout, full=True, build_date=BUILD_DATE)

    assert "baseline: (each at: 1)" in scripts[0]
    assert "#( #( 'Historia' 'tonel://" in scripts[0]
    assert "#( 'Historia-Core' 'Historia-Tests' )" in scripts[0]


def test_successful_build_replaces_current_snapshot(build_layout, monkeypatch):
    monkeypatch.setattr(snapshot, "run_pharo", fake_pharo_run(PASSED))

    build_snapshot(build_layout, full=True, build_date=BUILD_DATE)

    current_dir = build_layout.current_snapshot_dir
    assert image_path(current_dir).exists()
    assert not (current_dir / "pharo-local" / "iceberg").exists()
    assert not (current_dir / snapshot.TEST_RESULTS_FILE_NAME).exists()
    assert not list(current_dir.glob("*.st"))


def test_successful_build_writes_manifest(build_layout, monkeypatch):
    monkeypatch.setattr(snapshot, "run_pharo", fake_pharo_run(PASSED))

    build_snapshot(build_layout, full=True, build_date=BUILD_DATE)

    manifest = json.loads((build_layout.snapshots_dir / "2026-10-13.json").read_text())
    assert manifest == {
        "date": "2026-10-13",
        "mode": "full",
        "base": "dev-base",
        "repositories": [{"repository": "/repos/Historia", "baseline": "Historia", "sha": "abc123"}],
        "tests": PASSED,
    }


def test_successful_build_archives_snapshot_image(build_layout, monkeypatch):
    monkeypatch.setattr(snapshot, "run_pharo", fake_pharo_run(PASSED))

    build_snapshot(build_layout, full=True, build_date=BUILD_DATE)

    with tarfile.open(build_layout.archives_dir / "2026-10-13.tar.gz") as archive:
        assert "Pharo.image" in archive.getnames()


def test_failing_tests_keep_previous_snapshot(build_layout, monkeypatch):
    make_image_dir(build_layout.current_snapshot_dir)
    (build_layout.current_snapshot_dir / "Pharo.image").write_text("previous")
    failed = {"run": 2, "passed": 1, "failures": ["HistoriaTest>>#testA"], "errors": []}
    monkeypatch.setattr(snapshot, "run_pharo", fake_pharo_run(failed))

    with pytest.raises(SnapshotBuildError, match="HistoriaTest>>#testA"):
        build_snapshot(build_layout, full=True, build_date=BUILD_DATE)

    assert (build_layout.current_snapshot_dir / "Pharo.image").read_text() == "previous"
    assert not (build_layout.snapshots_dir / "2026-10-13.json").exists()
