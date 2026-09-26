"""The plugin's commands: `dashboard` (the pane process)."""

import copy
from datetime import datetime, timezone

from . import config, herdr_api, runtime, state, system, terminal, transcript


def _now():
    return datetime.now(timezone.utc)


def make_runtime(environ):
    """The Runtime of a plugin process: Herdr over `HERDR_SOCKET_PATH`, this machine's
    processes, the plugin's state directory, and transcripts read through a cache."""
    settings = copy.deepcopy(config.DEFAULTS)
    config_dir = state.claude_config_dir(environ, settings)
    summaries = transcript.Cache(transcript.load)
    return runtime.Runtime(
        herdr=herdr_api.Herdr.from_environ(environ), system=system.System(),
        paths=state.paths(environ, settings), settings=settings, clock=_now, environ=environ,
        summary_for=lambda session_id: summaries.get(transcript.find(config_dir, session_id)))


def main(args, environ):
    if args == ["dashboard"]:
        return terminal.run_dashboard(make_runtime(environ), environ.get("HERDR_PANE_ID"))
    return 2
