import json

import pytest

from pds.projects import DEFAULT_BRANCH, add_project_entry, branch_of, read_projects

ENTRY = {"repository": "/repos/a", "baseline": "A", "srcDir": "src", "groups": ["default"]}


def test_read_projects_requires_st_projects_json(layout):
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


def test_branch_of_defaults_to_develop():
    assert branch_of({}) == DEFAULT_BRANCH
    assert branch_of({"branch": ""}) == DEFAULT_BRANCH
    assert branch_of({"branch": "main"}) == "main"
