"""build-snapshot: load each project's origin branch into a copy of the base image,
run their tests, and promote the result to snapshots/current only when everything passes."""

import json
import tarfile
import tempfile
from datetime import datetime

from pds.image_dir import copy_image, image_path, remove_iceberg_cache, staged_replacement
from pds.pharo import build_sis_port, run_pharo
from pds.projects import branch_of, read_projects
from pds.sources import fetch_project_sources
from pds.st_script import FORGET_ICEBERG_CACHE_REPOSITORIES_SCRIPT, render_template_file

BUILD_SCRIPT_FILE_NAME = "build_snapshot.st"
TEST_RESULTS_FILE_NAME = "test-results.json"
BUILD_TIMEOUT_SECONDS = 3600


class SnapshotBuildError(RuntimeError):
    pass


class SnapshotTestFailure(SnapshotBuildError):
    """Tests failed after loading; snapshots/current is unchanged. `result` is the unsaved manifest."""

    def __init__(self, result):
        tests = result["tests"]
        failed = tests["failures"] + tests["errors"]
        super().__init__(
            f"{len(failed)} of {tests['run']} tests failed; snapshots/current is unchanged:\n  " + "\n  ".join(failed)
        )
        self.result = result


def load_script(fetched_sources):
    return render_template_file(
        "load_baselines.st",
        PROJECTS=[
            [source.project["baseline"], f"tonel://{source.src_path}", source.project["groups"]]
            for source in fetched_sources
        ],
        FORGET_ICEBERG_CACHE_REPOSITORIES_SCRIPT=str(FORGET_ICEBERG_CACHE_REPOSITORIES_SCRIPT),
    )


def test_packages(fetched_sources):
    """Package directories under each srcDir; run_tests.st skips those Metacello did not load (e.g. other platforms)."""
    return [
        package_dir.name
        for source in fetched_sources
        for package_dir in sorted(source.src_path.iterdir())
        if package_dir.is_dir() and not package_dir.name.startswith(("BaselineOf", "."))
    ]


def build_script(fetched_sources, build_dir):
    test_script = render_template_file(
        "run_tests.st",
        TEST_PACKAGES=test_packages(fetched_sources),
        RESULTS_FILE=str(build_dir / TEST_RESULTS_FILE_NAME),
    )
    return load_script(fetched_sources) + "\n" + test_script


def read_test_results(build_dir):
    results_file = build_dir / TEST_RESULTS_FILE_NAME
    test_results = json.loads(results_file.read_text())
    results_file.unlink()
    return test_results


def tests_failed(test_results):
    return bool(test_results["failures"] or test_results["errors"])


def manifest_for(built_at, mode, base, fetched_sources, test_results):
    return {
        "date": built_at.date().isoformat(),
        "builtAt": built_at.isoformat(timespec="seconds"),
        "mode": mode,
        "base": base,
        "repositories": [
            {
                "repository": source.project["repository"],
                "baseline": source.project["baseline"],
                "sha": source.sha,
                "branch": branch_of(source.project),
            }
            for source in fetched_sources
        ],
        "tests": test_results,
    }


def write_manifest(layout, manifest):
    (layout.snapshots_dir / f"{manifest['date']}.json").write_text(json.dumps(manifest, indent=2) + "\n")


def archive_current_snapshot(layout, build_date):
    layout.archives_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(layout.archives_dir / f"{build_date.isoformat()}.tar.gz", "w:gz") as archive:
        for path in sorted(layout.current_snapshot_dir.iterdir()):
            archive.add(path, arcname=path.name)


def latest_manifest_path(layout):
    manifests = sorted(layout.snapshots_dir.glob("*.json"))
    return manifests[-1] if manifests else None


def build_snapshot(layout, full=False, built_at=None):
    """Load every baseline with Metacello onto dev-base (full) or snapshots/current (incremental, default).

    Returns the manifest written to snapshots/<date>.json; raises SnapshotTestFailure carrying the
    unsaved manifest when tests fail."""
    built_at = built_at or datetime.now()
    projects = read_projects(layout)
    if full:
        mode, base, origin_dir = "full", "dev-base", layout.dev_base_dir
    else:
        if not image_path(layout.current_snapshot_dir).exists():
            raise SnapshotBuildError("snapshots/current does not exist; run `pds build-snapshot --full` first")
        previous_manifest_path = latest_manifest_path(layout)
        mode, origin_dir = "incremental", layout.current_snapshot_dir
        base = previous_manifest_path.stem if previous_manifest_path else None
    with tempfile.TemporaryDirectory(prefix="pds-sources-") as extract_root:
        fetched_sources = fetch_project_sources(projects, extract_root)
        with staged_replacement(layout.current_snapshot_dir, force=True) as build_dir:
            copy_image(layout, origin_dir, build_dir)
            script = build_dir / BUILD_SCRIPT_FILE_NAME
            script.write_text(build_script(fetched_sources, build_dir))
            run_pharo(
                layout, image_path(build_dir), script, port=build_sis_port(), timeout=BUILD_TIMEOUT_SECONDS, save=True
            )
            script.unlink()
            manifest = manifest_for(built_at, mode, base, fetched_sources, read_test_results(build_dir))
            if tests_failed(manifest["tests"]):
                raise SnapshotTestFailure(manifest)
            remove_iceberg_cache(build_dir)
    write_manifest(layout, manifest)
    archive_current_snapshot(layout, built_at.date())
    return manifest
