import shutil
import subprocess


def setup_plain(layout, version, force=False):
    """Download a plain Pharo image + VM from get.pharo.org into plain-pharo/."""
    if layout.plain_dir.exists():
        if not force:
            raise FileExistsError(f"{layout.plain_dir} already exists (use --force to replace it)")
        shutil.rmtree(layout.plain_dir)
    layout.plain_dir.mkdir(parents=True)
    subprocess.run(
        ["bash", "-c", f"curl -fsSL https://get.pharo.org/64/{version}+vm | bash"],
        cwd=layout.plain_dir,
        check=True,
    )
