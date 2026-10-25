"""Derive a st-projects.json entry from a repository: its BaselineOf name and srcDir.

Which packages to load (and in which order, per platform) is left to Metacello.
"""

import re
from pathlib import Path

SRC_DIRECTORY = re.compile(r"'srcDirectory'\s*:\s*'([^']*)'")
DEFAULT_GROUP = "default"


def src_dir_of(repository):
    project_file = repository / ".project"
    match = SRC_DIRECTORY.search(project_file.read_text()) if project_file.exists() else None
    return match.group(1) if match else "src"


def baseline_name_of(src_path):
    baseline_dirs = sorted(src_path.glob("BaselineOf*/"))
    if not baseline_dirs:
        raise FileNotFoundError(f"no BaselineOf* package under {src_path}")
    return baseline_dirs[0].name.removeprefix("BaselineOf")


def project_entry(repository, group_names=(DEFAULT_GROUP,)):
    repository = Path(repository).resolve()
    if not repository.is_dir():
        raise FileNotFoundError(f"repository {repository} does not exist")
    src_dir = src_dir_of(repository)
    return {
        "repository": str(repository),
        "baseline": baseline_name_of(repository / src_dir),
        "srcDir": src_dir,
        "groups": list(group_names),
    }
