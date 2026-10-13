from pathlib import Path

from pds.image_dir import copy_image, image_path, remove_iceberg_cache, staged_replacement
from pds.pharo import BUILD_SIS_PORT, run_pharo

PREPARE_DEV_BASE_SCRIPT = Path(__file__).parent / "st" / "prepare_dev_base.st"
METACELLO_LOAD_TIMEOUT_SECONDS = 1800


def prepare_dev_base(layout, force=False):
    """plain-pharo + SIS + AgenticBrowser -> dev-base/ (the origin of full snapshot builds)."""
    with staged_replacement(layout.dev_base_dir, force=force) as staging_dir:
        copy_image(layout, layout.plain_dir, staging_dir)
        run_pharo(
            layout,
            image_path(staging_dir),
            PREPARE_DEV_BASE_SCRIPT,
            port=BUILD_SIS_PORT,
            timeout=METACELLO_LOAD_TIMEOUT_SECONDS,
            save=True,
        )
        remove_iceberg_cache(staging_dir)
