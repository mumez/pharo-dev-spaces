import os
import subprocess

# SIS starts in every image we launch; builds use their own port so they never clash with slots or 8086.
BUILD_SIS_PORT = 8090


class PharoRunError(RuntimeError):
    pass


def pharo_command(layout, image, script, save=False):
    """Command line running `script` headless in `image` with the shared plain-pharo VM."""
    st_options = ["--save", "--quit"] if save else ["--quit"]
    return [str(layout.plain_dir / "pharo"), str(image), "st", *st_options, str(script)]


def run_pharo(layout, image, script, port, timeout, save=False):
    """Run an .st script headless; SIS in the image listens on `port` while it runs."""
    command = pharo_command(layout, image, script, save=save)
    environment = {**os.environ, "PHARO_SIS_PORT": str(port)}
    try:
        completed = subprocess.run(command, env=environment, timeout=timeout)
    except subprocess.TimeoutExpired as timeout_error:
        raise PharoRunError(f"{script} timed out after {timeout}s") from timeout_error
    if completed.returncode != 0:
        raise PharoRunError(f"{script} failed with exit code {completed.returncode}")
