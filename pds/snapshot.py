"""build-snapshot: load origin/develop of every project into a copy of the base image,
run their tests, and promote the result to snapshots/current only when everything passes."""

import json
import tarfile
import tempfile
from datetime import date

from pds.image_dir import copy_image, image_path, remove_iceberg_cache, staged_replacement
from pds.pharo import BUILD_SIS_PORT, run_pharo
from pds.projects import read_projects
from pds.sources import fetch_project_sources
from pds.st_script import render_template_file

BUILD_SCRIPT_FILE_NAME = "build_snapshot.st"
TEST_RESULTS_FILE_NAME = "test-results.json"
BUILD_TIMEOUT_SECONDS = 3600


class SnapshotBuildError(RuntimeError):
    pass


def full_load_script(fetched_sources):
    return render_template_file(
        "load_full.st",
        PROJECTS=[
            [source.project["baseline"], f"tonel://{source.src_path}", source.project["groups"]]
            for source in fetched_sources
        ],
    )


def test_packages(projects):
    return [
        package
        for project in projects
        for package in project["packages"]
        if not package.startswith("BaselineOf")
    ]


def build_script(load_script, projects, build_dir):
    test_script = render_template_file(
        "run_tests.st",
        TEST_PACKAGES=test_packages(projects),
        RESULTS_FILE=str(build_dir / TEST_RESULTS_FILE_NAME),
    )
    return load_script + "\n" + test_script


def read_test_results(build_dir):
    results_file = build_dir / TEST_RESULTS_FILE_NAME
    test_results = json.loads(results_file.read_text())
    results_file.unlink()
    failed = test_results["failures"] + test_results["errors"]
    if failed:
        raise SnapshotBuildError(
            f"{len(failed)} of {test_results['run']} tests failed; snapshots/current is unchanged:\n  "
            + "\n  ".join(failed)
        )
    return test_results


def write_manifest(layout, build_date, mode, base, fetched_sources, test_results):
    manifest = {
        "date": build_date.isoformat(),
        "mode": mode,
        "base": base,
        "repositories": [
            {"repository": source.project["repository"], "baseline": source.project["baseline"], "sha": source.sha}
            for source in fetched_sources
        ],
        "tests": test_results,
    }
    (layout.snapshots_dir / f"{build_date.isoformat()}.json").write_text(json.dumps(manifest, indent=2) + "\n")


def archive_current_snapshot(layout, build_date):
    layout.archives_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(layout.archives_dir / f"{build_date.isoformat()}.tar.gz", "w:gz") as archive:
        for path in sorted(layout.current_snapshot_dir.iterdir()):
            archive.add(path, arcname=path.name)


def build_snapshot(layout, full=False, build_date=None):
    build_date = build_date or date.today()
    projects = read_projects(layout)
    with tempfile.TemporaryDirectory(prefix="pds-sources-") as extract_root:
        fetched_sources = fetch_project_sources(projects, extract_root)
        with staged_replacement(layout.current_snapshot_dir, force=True) as build_dir:
            copy_image(layout, layout.dev_base_dir, build_dir)
            script = build_dir / BUILD_SCRIPT_FILE_NAME
            script.write_text(build_script(full_load_script(fetched_sources), projects, build_dir))
            run_pharo(
                layout, image_path(build_dir), script, port=BUILD_SIS_PORT, timeout=BUILD_TIMEOUT_SECONDS, save=True
            )
            script.unlink()
            test_results = read_test_results(build_dir)
            remove_iceberg_cache(build_dir)
    write_manifest(layout, build_date, "full", "dev-base", fetched_sources, test_results)
    archive_current_snapshot(layout, build_date)
