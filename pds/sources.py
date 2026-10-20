"""Snapshot sources: the srcDir of each repository at origin/develop, extracted without touching working trees."""

import io
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path

SNAPSHOT_BRANCH = "develop"


class SourceFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchedSource:
    project: dict
    sha: str
    src_path: Path


def git(repository, *arguments):
    completed = subprocess.run(["git", "-C", str(repository), *arguments], check=False, capture_output=True)
    if completed.returncode != 0:
        raise SourceFetchError(f"{repository}: git {' '.join(arguments)} failed: {completed.stderr.decode().strip()}")
    return completed.stdout


def fetch_develop_sha(repository):
    git(repository, "fetch", "--quiet", "origin", SNAPSHOT_BRANCH)
    return git(repository, "rev-parse", f"origin/{SNAPSHOT_BRANCH}").decode().strip()


def extract_src_dir(repository, sha, src_dir, target_dir):
    archive = git(repository, "archive", "--format=tar", sha, src_dir)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(target_dir, filter="data")
    return target_dir / src_dir


def fetch_project_sources(projects, extract_root):
    fetched_sources = []
    for project in projects:
        repository = project["repository"]
        sha = fetch_develop_sha(repository)
        src_path = extract_src_dir(repository, sha, project["srcDir"], Path(extract_root) / Path(repository).name)
        fetched_sources.append(FetchedSource(project, sha, src_path))
    return fetched_sources
