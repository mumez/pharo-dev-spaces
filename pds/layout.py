import os
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Layout:
    """Directory layout of a pharo-dev-spaces root (see README.md)."""

    root: Path

    @classmethod
    def default(cls):
        return cls(Path(os.environ.get("PDS_ROOT", REPOSITORY_ROOT)).resolve())

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
        return self.root / "projects.json"
