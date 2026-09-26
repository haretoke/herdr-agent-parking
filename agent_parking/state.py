"""Where the plugin keeps its state."""

import os
from pathlib import Path

PLUGIN_ID = "haretoke.agent-parking"


def state_dir(environ):
    """The directory Herdr gives this plugin, or the same path computed outside it.

    Herdr's own value is used only when it belongs to this plugin. Relative
    paths are ignored, as the XDG base directory spec asks.
    """
    own = environ.get("HERDR_PLUGIN_STATE_DIR", "")
    if environ.get("HERDR_PLUGIN_ID") == PLUGIN_ID and os.path.isabs(own):
        return Path(own)
    base = environ.get("XDG_STATE_HOME", "")
    if not os.path.isabs(base):
        base = os.path.join(environ.get("HOME") or str(Path.home()), ".local", "state")
    return Path(base) / "herdr" / "plugins" / PLUGIN_ID
