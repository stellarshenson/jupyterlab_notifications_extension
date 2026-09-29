"""Server configuration for integration tests.

!! Never use this configuration in production. It disables the token and the
XSRF check so Galata can drive the server, and it exposes JupyterLab's own
JavaScript objects on the global window variable. It stays bound to localhost.
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

from jupyterlab.galata import configure_jupyter_server

configure_jupyter_server(c)

# `or`, not a get() default: an exported-but-empty JUPYTER_TEST_PORT would
# raise here while Playwright waited happily on the default port.
c.ServerApp.port = int(os.environ.get("JUPYTER_TEST_PORT") or "8888")

# The fixtures each test removes go for good: a move to the trash fails on a
# root outside the home directory and leaves every fixture behind.
c.ContentsManager.delete_to_trash = False

# Serve ONLY this extension's labextension. This environment has ~40 other
# labextensions installed, and one of them opens a "Message of the day" tab on
# startup that becomes the active tab. Galata's waitForApplication waits for
# isTabActive('Launcher') before any test body runs, so a foreign tab stealing
# focus hangs the whole suite with a uniform timeout. Isolating the path also
# means a sibling extension breaking cannot fail this suite.

_here = Path(__file__).resolve().parent
_candidates = [
    _here.parent / "jupyterlab_notifications_extension" / "labextension",
    Path(sys.prefix) / "share/jupyter/labextensions/jupyterlab_notifications_extension",
]
_source = next((cand for cand in _candidates if cand.exists()), None)
if _source is None:
    raise RuntimeError(
        "no labextension build found in "
        + " or ".join(str(cand) for cand in _candidates)
        + "; run `jlpm build` or install the wheel first. Falling through would "
        "load every installed labextension and hang the suite on galata's "
        "isTabActive('Launcher') wait."
    )
_only = Path(tempfile.mkdtemp(prefix="galata-labext-"))
atexit.register(shutil.rmtree, _only, True)
os.symlink(_source, _only / "jupyterlab_notifications_extension")
c.LabServerApp.labextensions_path = [str(_only)]

# Uncomment to set server log level to debug level
# c.ServerApp.log_level = "DEBUG"
