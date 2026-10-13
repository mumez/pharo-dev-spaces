import os
import subprocess

# SIS starts in every image we launch; builds use their own port so they never clash with slots or 8086.
BUILD_SIS_PORT = 8090


class PharoRunError(RuntimeError):
    pass


def pharo_command(layout, image, *arguments):
    """Command line running `image` headless with the shared plain-pharo VM."""
    return [str(layout.plain_dir / "pharo"), str(image), *arguments]


def script_command(layout, image, script, save=False):
    st_options = ["--save", "--quit"] if save else ["--quit"]
    return pharo_command(layout, image, "st", *st_options, str(script))


def keep_alive_command(layout, image):
    return pharo_command(layout, image, "eval", "--no-quit", "nil")


def pharo_environment(port):
    """SIS in the image listens on `port` (read by SisSettings at startup)."""
    return {**os.environ, "PHARO_SIS_PORT": str(port)}


def run_pharo(layout, image, script, port, timeout, save=False):
    """Run an .st script headless and wait for the image to quit."""
    command = script_command(layout, image, script, save=save)
    try:
        completed = subprocess.run(command, env=pharo_environment(port), timeout=timeout)
    except subprocess.TimeoutExpired as timeout_error:
        raise PharoRunError(f"{script} timed out after {timeout}s") from timeout_error
    if completed.returncode != 0:
        raise PharoRunError(f"{script} failed with exit code {completed.returncode}")
