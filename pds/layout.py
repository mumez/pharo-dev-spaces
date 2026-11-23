import os
from dataclasses import dataclass
from pathlib import Path

from pds.config import find_config_file, load_config

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Layout:
    """Directory layout of a pharo-dev-spaces root (see README.md)."""

    root: Path

    @classmethod
    def default(cls):
        return cls(resolved_root()["value"])

    @property
    def plain_dir(self):
        return self.root / "plain-pharo"

    @property
    def dev_base_dir(self):
        return self.root / "dev-base"

    @property
    def slots_dir(self):
        return self.root / "slots"

    @property
    def snapshots_dir(self):
        return self.root / "snapshots"

    @property
    def current_snapshot_dir(self):
        return self.snapshots_dir / "current"

    @property
    def archives_dir(self):
        return self.root / "archives"

    @property
    def projects_file(self):
        return self.root / "st-projects.json"


def resolved_root():
    """{"value", "source"} of the pds root: PDS_ROOT > the nearest pds.json's directory > REPOSITORY_ROOT."""
    if os.environ.get("PDS_ROOT"):
        return {"value": Path(os.environ["PDS_ROOT"]).resolve(), "source": "env:PDS_ROOT"}
    config_file = find_config_file()
    if config_file:
        return {"value": load_config(config_file)["directory"], "source": f"pds.json:{config_file}"}
    return {"value": REPOSITORY_ROOT, "source": "default"}
