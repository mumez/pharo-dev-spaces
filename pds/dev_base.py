from pathlib import Path

from pds.image_dir import copy_image, image_path, remove_iceberg_cache, staged_replacement
from pds.pharo import BUILD_SIS_PORT, STANDALONE_SIS_PORT, launch_pharo_ui, run_pharo

# AgenticBrowser baseline pulls SIS; the .st itself snapshots and quits.
LOAD_AGENTIC_BROWSER_SCRIPT = Path(__file__).parent / "st" / "load_agentic_browser.st"
METACELLO_LOAD_TIMEOUT_SECONDS = 1800


def prepare_dev_base(layout, force=False):
    """plain-pharo + AgenticBrowser (incl. SIS) -> dev-base/.

    Equivalent to copying the plain image, then:
      ./pharo Pharo.image st pds/st/load_agentic_browser.st
    """
    with staged_replacement(layout.dev_base_dir, force=force) as staging_dir:
        copy_image(layout, layout.plain_dir, staging_dir)
        run_pharo(
            layout,
            image_path(staging_dir),
            LOAD_AGENTIC_BROWSER_SCRIPT,
            port=BUILD_SIS_PORT,
            timeout=METACELLO_LOAD_TIMEOUT_SECONDS,
            save=None,
        )
        remove_iceberg_cache(staging_dir)


def run_dev_base(layout):
    """Open dev-base in the GUI (verification). Replaces this process; SIS on port 8086."""
    image = image_path(layout.dev_base_dir)
    if not image.exists():
        raise FileNotFoundError(f"{image} does not exist; run `pds prepare-dev-base` first")
    launch_pharo_ui(layout, image, STANDALONE_SIS_PORT)
