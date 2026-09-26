"""Where the plugin keeps its state."""

import os
from collections import namedtuple
from pathlib import Path

PLUGIN_ID = "haretoke.agent-parking"

Paths = namedtuple("Paths", "records resumed observed log")


def home(environ):
    return environ.get("HOME") or str(Path.home())


def expand_home(path, environ):
    """`path` with a leading `~` replaced by the `HOME` in `environ`."""
    if path == "~" or path.startswith("~/"):
        return Path(home(environ) + path[1:])
    return Path(path)


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
        base = os.path.join(home(environ), ".local", "state")
    return Path(base) / "herdr" / "plugins" / PLUGIN_ID


def paths(environ, settings):
    """Where each file lives. `records_dir` moves the records (parked and resumed) only."""
    own = state_dir(environ)
    records_root = own
    if settings["records_dir"]:
        records_root = expand_home(settings["records_dir"], environ)
    return Paths(records=records_root / "records", resumed=records_root / "resumed",
                 observed=own / "observed.json", log=own / "dashboard.log")


def claude_config_dir(environ, settings):
    """Where Claude Code keeps `projects/*/<uuid>.jsonl`: the setting, then an absolute
    `CLAUDE_CONFIG_DIR`, then `~/.claude`."""
    if settings["claude_config_dir"]:
        return expand_home(settings["claude_config_dir"], environ)
    given = environ.get("CLAUDE_CONFIG_DIR", "")
    if os.path.isabs(given):
        return Path(given)
    return Path(home(environ)) / ".claude"
