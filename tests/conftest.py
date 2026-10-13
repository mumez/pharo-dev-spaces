from pathlib import Path

import pytest

from pds.layout import Layout

REPO_ROOT = Path(__file__).resolve().parents[1]


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
