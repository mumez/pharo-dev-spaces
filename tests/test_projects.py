import json

import pytest

from pds.projects import add_project_entry, read_projects

ENTRY = {"repository": "/repos/a", "baseline": "A", "srcDir": "src", "groups": ["default"], "packages": ["BaselineOfA"]}


def test_read_projects_requires_projects_json(layout):
    with pytest.raises(FileNotFoundError, match="add-project"):
        read_projects(layout)


def test_add_project_entry_appends_in_order(layout):
    add_project_entry(layout, ENTRY)
    add_project_entry(layout, {**ENTRY, "repository": "/repos/b"})

    assert [entry["repository"] for entry in read_projects(layout)] == ["/repos/a", "/repos/b"]
    assert json.loads(layout.projects_file.read_text())[0] == ENTRY


def test_add_project_entry_rejects_registered_repository(layout):
    add_project_entry(layout, ENTRY)

    with pytest.raises(ValueError, match="already"):
        add_project_entry(layout, ENTRY)
