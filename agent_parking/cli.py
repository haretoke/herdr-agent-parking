"""The plugin's commands: `dashboard` (the pane process), `open` and `open-tab` (the
plugin actions that open it)."""

import sys
import traceback
from datetime import datetime, timezone

from . import config, herdr_api, logfile, runtime, state, system, terminal, transcript


def _now():
    return datetime.now(timezone.utc)


def make_runtime(environ):
    """The Runtime of a plugin process: Herdr over `HERDR_SOCKET_PATH`, this machine's
    processes, the plugin's state directory, and transcripts read through a cache."""
    log = state.state_dir(environ) / "dashboard.log"
    settings = config.load(state.config_dir(environ) / "config.json", lambda line: logfile.append(log, line))
    config_dir = state.claude_config_dir(environ, settings)
    summaries = transcript.Cache(transcript.load)

    def rows_for(session_id):
        """The tail of the session's transcript (the compact flow reads Claude's replies)."""
        path = transcript.find(config_dir, session_id)
        try:
            return transcript.read_tail(path) if path is not None else []
        except OSError:
            return []

    paths = state.paths(environ, settings)
    return runtime.Runtime(
        herdr=herdr_api.Herdr.from_environ(environ), system=system.System(),
        paths=paths, settings=settings, clock=_now, environ=environ,
        summary_for=lambda session_id: summaries.get(transcript.find(config_dir, session_id)),
        rows_for=rows_for,
        statusline_windows=transcript.statusline_windows(paths.windows))


def main(args, environ):
    if args == ["dashboard"]:
        rt = make_runtime(environ)
        try:
            return terminal.run_dashboard(rt, environ.get("HERDR_PANE_ID"))
        except Exception:
            logfile.append(rt.paths.log, "dashboard error\n" + traceback.format_exc())
            return 1
    if args in (["open"], ["open-tab"]):
        return _open(environ, tab=args == ["open-tab"])
    return 2


def _open(environ, tab):
    """The `open` action: the dashboard over the active pane (overlay); `open-tab`: in a
    new tab of the current workspace, for people who keep it open."""
    params = {"plugin_id": state.PLUGIN_ID, "entrypoint": "dashboard", "placement": "tab" if tab else "overlay",
              "focus": True}
    if tab and environ.get("HERDR_WORKSPACE_ID"):
        params["workspace_id"] = environ["HERDR_WORKSPACE_ID"]
    try:
        herdr_api.Herdr.from_environ(environ).call("plugin.pane.open", params)
    except herdr_api.HerdrError as error:
        return fail(error)
    return 0


def fail(message):
    print("agent-parking: %s" % message, file=sys.stderr)
    return 1
