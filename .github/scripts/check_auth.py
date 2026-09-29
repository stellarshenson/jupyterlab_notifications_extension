"""Check that all endpoints of the extension require authentication.

When unauthenticated access is not allowed, Jupyter Server warns about every
handler which is missing an authentication decorator; this script turns such a
warning into a failure, so that no endpoint can be exposed to unauthorized users
by mistake.

Run it with:

    python .github/scripts/check_auth.py
"""
import os
import sys
import warnings

# Before importing jupyter_server: initialize() executes any
# jupyter_server_config.py on the config path, INSIDE the catch_warnings block
# below, so such a file could call warnings.simplefilter("ignore") and silence
# the very warning this gate reads - the argv form below does not help, because
# the surface is the filter list, not the trait. It could also turn off
# reraise_server_extension_failures. With no config path, none of it runs.
# Assigned, not setdefault: jupyter_core tests this for truthiness, so an
# exported empty JUPYTER_NO_CONFIG= would survive setdefault, be falsy, and
# re-open the config path this line exists to close. The gate has no caller
# that wants outside config, so there is nothing to defer to.
os.environ["JUPYTER_NO_CONFIG"] = "1"

from jupyter_server.serverapp import ServerApp
from jupyter_server.utils import JupyterServerAuthWarning

# Initialize a server which only loads this extension and which does not allow
# unauthenticated access.
app = ServerApp(
    jpserver_extensions={"jupyterlab_notifications_extension": True},
    # Fail loudly if the extension cannot be loaded at all, instead of silently
    # reporting that there is nothing to complain about.
    reraise_server_extension_failures=True,
)

with warnings.catch_warnings(record=True) as records:
    warnings.simplefilter("always")
    # Load-bearing, and not a duplicate of JUPYTER_NO_CONFIG above: this sets
    # the trait, that one only stops config files. allow_unauthenticated_access
    # defaults True, and jupyter_server emits the warning this gate reads only
    # when it is False (serverapp.py), so without this line no warning is ever
    # recorded and the gate passes an undecorated endpoint. On the command line
    # rather than as a constructor kwarg, because CLI config is applied last
    # and so also outranks JUPYTER_SERVER_ALLOW_UNAUTHENTICATED_ACCESS.
    app.initialize(
        argv=["--ServerApp.allow_unauthenticated_access=False"],
        find_extensions=False,
        new_httpserver=False,
    )

problems = [
    str(record.message)
    for record in records
    if issubclass(record.category, JupyterServerAuthWarning)
]

if problems:
    sys.exit(
        "\n".join(problems)
        + "\n\nAdd a `@tornado.web.authenticated` decorator to the verb methods listed"
        " above. If an endpoint is intended to be public, add an explicit"
        " `@allow_unauthenticated` (or `@ws_authenticated` for websockets) decorator"
        " from `jupyter_server.auth.decorator` instead."
    )

print("All endpoints of the extension require authentication.")
