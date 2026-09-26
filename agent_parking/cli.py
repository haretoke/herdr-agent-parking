"""The plugin's commands: `dashboard` (the pane process)."""

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

    return runtime.Runtime(
        herdr=herdr_api.Herdr.from_environ(environ), system=system.System(),
        paths=state.paths(environ, settings), settings=settings, clock=_now, environ=environ,
        summary_for=lambda session_id: summaries.get(transcript.find(config_dir, session_id)),
        rows_for=rows_for,
        statusline_windows=transcript.statusline_windows(state.state_dir(environ) / "context-windows.json"))


def main(args, environ):
    if args == ["dashboard"]:
        rt = make_runtime(environ)
        try:
            return terminal.run_dashboard(rt, environ.get("HERDR_PANE_ID"))
        except Exception:
            logfile.append(rt.paths.log, "dashboard error\n" + traceback.format_exc())
            return 1
    return 2
