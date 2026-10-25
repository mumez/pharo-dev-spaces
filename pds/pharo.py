import os
import socket
import subprocess

# SIS starts in every image we launch; builds use their own port so they never clash with slots or 8086.
STANDALONE_SIS_PORT = 8086  # reserved for a lone GUI/headless image (e.g. run-dev-base)
BUILD_SIS_PORT = 8096
# Ripple (AgenticBrowser WebUI) also listens in every image; keep it next to the SIS port so images never share it.
RIPPLE_PORT_OFFSET_FROM_SIS = 1000


class PharoRunError(RuntimeError):
    pass


class PortInUseError(RuntimeError):
    pass


def pharo_command(layout, image, *arguments):
    """Command line running `image` headless with the shared plain-pharo VM."""
    return [str(layout.plain_dir / "pharo"), str(image), *arguments]


def pharo_ui_command(layout, image, *arguments):
    """Command line running `image` with the GUI VM (plain-pharo/pharo-ui)."""
    return [str(layout.plain_dir / "pharo-ui"), str(image), *arguments]


def launch_pharo_ui(layout, image, port):
    """Replace this process with a GUI Pharo listening on `port`."""
    command = pharo_ui_command(layout, image)
    os.execvpe(command[0], command, pharo_environment(port))


def script_command(layout, image, script, save=False):
    """Build `pharo image st [...] script`.

    save=True  -> st --save --quit
    save=False -> st --quit
    save=None  -> st <script> only (script handles snapshot/quit, e.g. load_agentic_browser.st)
    """
    if save is None:
        return pharo_command(layout, image, "st", str(script))
    st_options = ["--save", "--quit"] if save else ["--quit"]
    return pharo_command(layout, image, "st", *st_options, str(script))


def keep_alive_command(layout, image):
    return pharo_command(layout, image, "eval", "--no-quit", "nil")


def default_ripple_port(sis_port):
    return sis_port + RIPPLE_PORT_OFFSET_FROM_SIS


def pharo_environment(port, ripple_port=None):
    """SIS listens on `port` and Ripple on `ripple_port` (default `port` + 1000), read at image startup."""
    return {
        **os.environ,
        "PHARO_SIS_PORT": str(port),
        "PHARO_RIPPLE_PORT": str(default_ripple_port(port) if ripple_port is None else ripple_port),
    }


def ensure_pharo_ports_available(environment):
    """Fail before launch: a busy port only shows up as a debugger inside the image (invisible when headless)."""
    for role, variable in (("SIS", "PHARO_SIS_PORT"), ("Ripple", "PHARO_RIPPLE_PORT")):
        role_port = int(environment[variable])
        if not is_port_available(role_port):
            raise PortInUseError(f"{role} port {role_port} is already in use by another process")


def is_port_available(port):
    """Bind like Pharo does (all interfaces); SO_REUSEADDR ignores sockets left in TIME_WAIT by a stopped image."""
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def run_pharo(layout, image, script, port, timeout, save=False):
    """Run an .st script headless and wait for the image to quit."""
    command = script_command(layout, image, script, save=save)
    try:
        completed = subprocess.run(command, check=False, env=pharo_environment(port), timeout=timeout)
    except subprocess.TimeoutExpired as timeout_error:
        raise PharoRunError(f"{script} timed out after {timeout}s") from timeout_error
    if completed.returncode != 0:
        raise PharoRunError(f"{script} failed with exit code {completed.returncode}")
