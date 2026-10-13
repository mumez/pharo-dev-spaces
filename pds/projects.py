"""projects.json: repositories (and their packages) in load order."""

import json


def read_projects(layout):
    if not layout.projects_file.exists():
        raise FileNotFoundError(f"{layout.projects_file} does not exist; register repositories with `pds add-project`")
    return json.loads(layout.projects_file.read_text())


def write_projects(layout, projects):
    layout.projects_file.write_text(json.dumps(projects, indent=2) + "\n")


def add_project_entry(layout, entry):
    projects = read_projects(layout) if layout.projects_file.exists() else []
    if any(project["repository"] == entry["repository"] for project in projects):
        raise ValueError(f"{entry['repository']} is already in {layout.projects_file}")
    write_projects(layout, [*projects, entry])
