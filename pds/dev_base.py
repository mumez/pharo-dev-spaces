import tempfile
from pathlib import Path

from pds.image_dir import copy_image, image_path, remove_iceberg_cache, staged_replacement
from pds.pharo import BUILD_SIS_PORT, STANDALONE_SIS_PORT, launch_pharo_ui, run_pharo
from pds.st_script import TEMPLATE_DIR, render_template_file

# load_libs.st files in every libs/*.st in name order (001_agentic_browser.st pulls SIS), then snapshots and quits.
DEV_BASE_LIBS_DIR = TEMPLATE_DIR / "libs"
LOAD_LIBS_TEMPLATE = "load_libs.st"
METACELLO_LOAD_TIMEOUT_SECONDS = 1800


def load_libs_script(libs_dir=DEV_BASE_LIBS_DIR):
    return render_template_file(LOAD_LIBS_TEMPLATE, LIBS_DIR=str(libs_dir))


def prepare_dev_base(layout, force=False):
    """plain-pharo + pds/st/libs/*.st (AgenticBrowser incl. SIS, plus any user libs) -> dev-base/.

    Equivalent to copying the plain image, then:
      ./pharo Pharo.image st load_libs.st   (rendered with the libs directory)
    """
    with (
        staged_replacement(layout.dev_base_dir, force=force) as staging_dir,
        tempfile.TemporaryDirectory(prefix="pds-dev-base-") as script_dir,
    ):
        copy_image(layout, layout.plain_dir, staging_dir)
        script = Path(script_dir) / LOAD_LIBS_TEMPLATE
        script.write_text(load_libs_script())
        run_pharo(
            layout,
            image_path(staging_dir),
            script,
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
