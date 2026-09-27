"""Where the plugin keeps its state."""

import os
from collections import namedtuple
from pathlib import Path

PLUGIN_ID = "haretoke.agent-parking"

Paths = namedtuple("Paths", "records resumed observed log windows dashboard")


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
    return _plugin_dir(environ, "HERDR_PLUGIN_STATE_DIR", "XDG_STATE_HOME", (".local", "state"),
                       ("herdr", "plugins", PLUGIN_ID))


def _plugin_dir(environ, own_name, xdg_name, xdg_default, under_xdg):
    own = environ.get(own_name, "")
    if environ.get("HERDR_PLUGIN_ID") == PLUGIN_ID and os.path.isabs(own):
        return Path(own)
    base = environ.get(xdg_name, "")
    if not os.path.isabs(base):
        base = os.path.join(home(environ), *xdg_default)
    return Path(base).joinpath(*under_xdg)


def config_dir(environ):
    """Where `config.json` lives: the directory Herdr gives this plugin, or the same path
    outside it (what `herdr plugin config-dir <id>` prints), so the shell subcommands read
    the file the dashboard reads."""
    return _plugin_dir(environ, "HERDR_PLUGIN_CONFIG_DIR", "XDG_CONFIG_HOME", (".config",),
                       ("herdr", "plugins", "config", PLUGIN_ID))


def dashboard_pane(environ):
    """The pane this process draws the dashboard in, or None for the shell commands."""
    if environ.get("HERDR_PLUGIN_ID") == PLUGIN_ID and environ.get("HERDR_PLUGIN_ENTRYPOINT_ID") == "dashboard":
        return environ.get("HERDR_PANE_ID") or None
    return None


def paths(environ, settings):
    """Where each file lives. `records_dir` moves the records (parked and resumed) only."""
    own = state_dir(environ)
    records_root = own
    if settings["records_dir"]:
        records_root = expand_home(settings["records_dir"], environ)
    return Paths(records=records_root / "records", resumed=records_root / "resumed",
                 observed=own / "observed.json", log=own / "dashboard.log",
                 windows=own / "context-windows.json", dashboard=own / "dashboard.json")


def claude_config_dir(environ, settings):
    """Where Claude Code keeps `projects/*/<uuid>.jsonl`: the setting, then an absolute
    `CLAUDE_CONFIG_DIR`, then `~/.claude`."""
    if settings["claude_config_dir"]:
        return expand_home(settings["claude_config_dir"], environ)
    given = environ.get("CLAUDE_CONFIG_DIR", "")
    if os.path.isabs(given):
        return Path(given)
    return Path(home(environ)) / ".claude"
