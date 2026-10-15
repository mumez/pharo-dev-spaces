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
}


def fake_fetch_project_sources(projects, extract_root):
    src_path = Path(extract_root) / "Historia" / "src"
    for package in ("BaselineOfHistoria", "Historia-Core", "Historia-Tests"):
        (src_path / package).mkdir(parents=True)
    (src_path / ".properties").write_text("{}")
    return [FetchedSource(PROJECT, "abc123", src_path)]


@pytest.fixture
def build_layout(layout, monkeypatch):
    make_image_dir(layout.plain_dir)
    make_image_dir(layout.dev_base_dir)
    layout.projects_file.write_text(json.dumps([PROJECT]))
    monkeypatch.setattr(snapshot, "fetch_project_sources", fake_fetch_project_sources)
    return layout


def fake_pharo_run(test_results, runs=None):
    def run(layout, image, script, port, timeout, save=False):
        if runs is not None:
            runs.append({"image": image.read_text(), "script": script.read_text()})
        (image.parent / "pharo-local" / "iceberg").mkdir(parents=True, exist_ok=True)
        (image.parent / snapshot.TEST_RESULTS_FILE_NAME).write_text(json.dumps(test_results))

    return run


PASSED = {"run": 2, "passed": 2, "failures": [], "errors": []}


def test_full_build_loads_baselines_with_metacello_onto_dev_base(build_layout, monkeypatch):
    (build_layout.dev_base_dir / "Pharo.image").write_text("dev-base")
    runs = []
    monkeypatch.setattr(snapshot, "run_pharo", fake_pharo_run(PASSED, runs))

    build_snapshot(build_layout, full=True, build_date=BUILD_DATE)

    assert runs[0]["image"] == "dev-base"
    assert "baseline: (each at: 1)" in runs[0]["script"]
    assert "#( #( 'Historia' 'tonel://" in runs[0]["script"]
    assert "#( 'default' ) ) ) do:" in runs[0]["script"]


def test_build_tests_package_directories_of_src_dir_except_baseline(build_layout, monkeypatch):
    runs = []
    monkeypatch.setattr(snapshot, "run_pharo", fake_pharo_run(PASSED, runs))

    build_snapshot(build_layout, full=True, build_date=BUILD_DATE)

    assert "#( 'Historia-Core' 'Historia-Tests' ) do: [ :packageName |" in runs[0]["script"]


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


def make_current_snapshot(layout, manifest_date="2026-10-12"):
    make_image_dir(layout.current_snapshot_dir)
    (layout.current_snapshot_dir / "Pharo.image").write_text("current")
    repositories = [{"repository": PROJECT["repository"], "sha": "abc123"}]
    layout.snapshots_dir.joinpath(f"{manifest_date}.json").write_text(json.dumps({"repositories": repositories}))


def test_incremental_build_loads_baselines_with_metacello_onto_current_snapshot(build_layout, monkeypatch):
    make_current_snapshot(build_layout)
    runs = []
    monkeypatch.setattr(snapshot, "run_pharo", fake_pharo_run(PASSED, runs))

    build_snapshot(build_layout, build_date=BUILD_DATE)

    assert runs[0]["image"] == "current"
    assert "#( #( 'Historia' 'tonel://" in runs[0]["script"]


def test_incremental_manifest_records_previous_snapshot_as_base(build_layout, monkeypatch):
    make_current_snapshot(build_layout, "2026-10-12")
    monkeypatch.setattr(snapshot, "run_pharo", fake_pharo_run(PASSED))

    build_snapshot(build_layout, build_date=BUILD_DATE)

    manifest = json.loads((build_layout.snapshots_dir / "2026-10-13.json").read_text())
    assert manifest["mode"] == "incremental"
    assert manifest["base"] == "2026-10-12"


def test_incremental_build_requires_current_snapshot(build_layout):
    with pytest.raises(SnapshotBuildError, match="--full"):
        build_snapshot(build_layout, build_date=BUILD_DATE)


TONEL_BASELINE = """Class {
	#name : 'BaselineOfPdsProbe',
	#superclass : 'BaselineOf',
	#category : 'BaselineOfPdsProbe',
	#package : 'BaselineOfPdsProbe'
}

{ #category : 'baselines' }
BaselineOfPdsProbe >> baseline: spec [
	<baseline>
	spec for: #common do: [ spec package: 'PdsProbe' ]
]
"""
TONEL_CLASS = """Class {{
	#name : 'PdsProbe',
	#superclass : 'Object',
	#category : 'PdsProbe',
	#package : 'PdsProbe'
}}
{methods}"""
TONEL_METHOD = """
{{ #category : 'probe' }}
PdsProbe >> {selector} [
	^ 1
]
"""


def write_probe_repository(src_dir, selectors):
    for package in ("BaselineOfPdsProbe", "PdsProbe"):
        (src_dir / package).mkdir(parents=True, exist_ok=True)
        (src_dir / package / "package.st").write_text(f"Package {{ #name : '{package}' }}\n")
    (src_dir / "BaselineOfPdsProbe" / "BaselineOfPdsProbe.class.st").write_text(TONEL_BASELINE)
    methods = "".join(TONEL_METHOD.format(selector=selector) for selector in selectors)
    (src_dir / "PdsProbe" / "PdsProbe.class.st").write_text(TONEL_CLASS.format(methods=methods))


@pytest.mark.pharo
def test_reloading_a_baseline_applies_added_and_removed_methods(pharo_layout, tmp_path):
    from pds.image_dir import copy_image
    from pds.pharo import run_pharo

    image_dir = tmp_path / "image"
    copy_image(pharo_layout, pharo_layout.plain_dir, image_dir)
    src_dir = tmp_path / "src"
    result_file = tmp_path / "selectors.txt"
    script = tmp_path / "load.st"
    probe_source = FetchedSource({"baseline": "PdsProbe", "groups": ["default"]}, "sha", src_dir)

    def load_and_list_selectors():
        script.write_text(
            snapshot.load_script([probe_source])
            + f"\n'{result_file}' asFileReference ensureDelete; writeStreamDo: [ :s | "
            "s nextPutAll: ((Smalltalk at: #PdsProbe) selectors sorted joinUsing: ' ') ]."
        )
        run_pharo(pharo_layout, image_dir / "Pharo.image", script, port=8091, timeout=120, save=True)
        return result_file.read_text().split()

    write_probe_repository(src_dir, ["kept", "removed"])
    assert load_and_list_selectors() == ["kept", "removed"]

    write_probe_repository(src_dir, ["kept", "added"])
    assert load_and_list_selectors() == ["added", "kept"]
