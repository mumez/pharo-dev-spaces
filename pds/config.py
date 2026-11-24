"""Per-repository `pds.json`: which pds root and ports a repository uses (see README.md)."""

import json
from pathlib import Path

CONFIG_FILE_NAME = "pds.json"
CONFIG_KEYS = {"directory", "ports"}
PORT_KEYS = {"devBasePort", "slotStartPort", "buildPort"}


def find_config_file():
    """The nearest `pds.json` in the cwd or its parents, or None."""
    cwd = Path.cwd()
    for directory in (cwd, *cwd.parents):
        config_file = directory / CONFIG_FILE_NAME
        if config_file.is_file():
            return config_file
    return None


def nearest_config():
    """The nearest pds.json loaded once: {"file", "directory", "ports"}, or {"file": None, "ports": {}} without one."""
    config_file = find_config_file()
    if config_file is None:
        return {"file": None, "ports": {}}
    return {"file": config_file, **load_config(config_file)}


def load_config(config_file):
    """{"directory": absolute pds root, "ports": {key: value}} from `config_file`; port ranges are checked by users."""
    try:
        config = json.loads(config_file.read_text())
    except json.JSONDecodeError as syntax_error:
        raise ValueError(f"{config_file}: {syntax_error}") from syntax_error
    if not isinstance(config, dict) or not isinstance(config.get("directory"), str):
        raise ValueError(f'{config_file}: "directory" (a path string) is required')  # noqa: TRY004 - bad config value
    reject_unknown_keys(config_file, config, CONFIG_KEYS)
    ports = config.get("ports", {})
    if not isinstance(ports, dict):
        raise ValueError(f'{config_file}: "ports" must be an object')  # noqa: TRY004
    reject_unknown_keys(config_file, ports, PORT_KEYS)
    directory = (config_file.parent / config["directory"]).resolve()
    if not directory.is_dir():
        raise ValueError(f"{config_file}: directory {directory} does not exist")
    return {"directory": directory, "ports": ports}


def reject_unknown_keys(config_file, mapping, known_keys):
    unknown_keys = mapping.keys() - known_keys
    if unknown_keys:
        raise ValueError(f"{config_file}: unknown keys {sorted(unknown_keys)}; expected {sorted(known_keys)}")
