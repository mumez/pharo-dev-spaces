import json

import pytest

from pds.config import find_config_file, load_config


def write_config(directory, config):
    config_file = directory / "pds.json"
    config_file.write_text(json.dumps(config))
    return config_file


def test_config_file_is_found_in_a_parent_of_the_cwd(tmp_path, monkeypatch):
    config_file = write_config(tmp_path, {"directory": "."})
    nested_dir = tmp_path / "src" / "Package"
    nested_dir.mkdir(parents=True)
    monkeypatch.chdir(nested_dir)

    assert find_config_file() == config_file


def test_nearest_config_file_wins(tmp_path, monkeypatch):
    write_config(tmp_path, {"directory": "."})
    repository_dir = tmp_path / "repo"
    repository_dir.mkdir()
    nearest_config_file = write_config(repository_dir, {"directory": "."})
    monkeypatch.chdir(repository_dir)

    assert find_config_file() == nearest_config_file


def test_no_config_file_gives_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert find_config_file() is None


def test_relative_directory_is_resolved_from_the_config_file(tmp_path):
    pds_root = tmp_path / "pds-root"
    pds_root.mkdir()
    repository_dir = tmp_path / "repo"
    repository_dir.mkdir()
    config_file = write_config(repository_dir, {"directory": "../pds-root"})

    assert load_config(config_file) == {"directory": pds_root, "ports": {}}


def test_absolute_directory_and_ports_are_loaded(tmp_path):
    config_file = write_config(
        tmp_path, {"directory": str(tmp_path), "ports": {"devBasePort": 2001, "buildPort": 2010}}
    )

    assert load_config(config_file) == {"directory": tmp_path, "ports": {"devBasePort": 2001, "buildPort": 2010}}


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({}, "directory"),
        ({"directory": 1}, "directory"),
        ({"directory": "missing"}, "does not exist"),
        ({"directory": ".", "port": {}}, "unknown keys"),
        ({"directory": ".", "ports": {"slotPort": 2002}}, "unknown keys"),
        ({"directory": ".", "ports": []}, "ports"),
    ],
)
def test_invalid_config_is_rejected(tmp_path, config, message):
    config_file = write_config(tmp_path, config)

    with pytest.raises(ValueError, match=message):
        load_config(config_file)


def test_malformed_json_is_rejected_with_the_file_name(tmp_path):
    config_file = tmp_path / "pds.json"
    config_file.write_text("{")

    with pytest.raises(ValueError, match="pds.json"):
        load_config(config_file)
