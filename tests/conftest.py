import json
from pathlib import Path

import pytest

from pds.layout import Layout

REPO_ROOT = Path(__file__).resolve().parents[1]
PORT_ENVIRONMENT_VARIABLES = ("PDS_DEV_BASE_PORT", "PDS_SLOT_START_PORT", "PDS_BUILD_PORT")


@pytest.fixture(autouse=True)
def default_pds_ports(monkeypatch):
    """Tests expect the default root and ports regardless of the developer's shell."""
    for variable in ("PDS_ROOT", *PORT_ENVIRONMENT_VARIABLES):
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture
def write_pds_json(tmp_path, monkeypatch):
    """Write tmp_path/pds.json and run the test from tmp_path; the pds root is tmp_path/pds-root."""
    (tmp_path / "pds-root").mkdir()
    monkeypatch.chdir(tmp_path)

    def write(ports=None):
        config = {"directory": "pds-root"} if ports is None else {"directory": "pds-root", "ports": ports}
        config_file = tmp_path / "pds.json"
        config_file.write_text(json.dumps(config))
        return config_file

    return write


@pytest.fixture
def layout(tmp_path):
    return Layout(tmp_path)


@pytest.fixture
def pharo_layout(tmp_path):
    """A layout whose plain-pharo is the repository's real one (VM shared via symlink)."""
    real_plain_dir = REPO_ROOT / "plain-pharo"
    if not (real_plain_dir / "Pharo.image").exists():
        pytest.skip("plain-pharo is not set up; run `pds setup-plain` first")
    tmp_layout = Layout(tmp_path)
    tmp_layout.plain_dir.symlink_to(real_plain_dir)
    return tmp_layout


@pytest.fixture
def dev_base_layout(pharo_layout):
    """pharo_layout plus the repository's real dev-base (with SIS)."""
    real_dev_base_dir = REPO_ROOT / "dev-base"
    if not (real_dev_base_dir / "Pharo.image").exists():
        pytest.skip("dev-base is not prepared; run `pds prepare-dev-base` first")
    pharo_layout.dev_base_dir.symlink_to(real_dev_base_dir)
    return pharo_layout
