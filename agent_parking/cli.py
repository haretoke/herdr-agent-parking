"""The plugin's commands: `dashboard` (the pane process), `open` and `open-tab` (the
plugin actions that open it), `list` (the rows as JSON for scripts)."""

import argparse
import dataclasses
import json
import sys
import traceback
from datetime import datetime, timezone

from . import config, herdr_api, idle, inventory, logfile, runtime, state, system, terminal, transcript


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
    parser = argparse.ArgumentParser(prog="agent-parking")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("dashboard", help="run the dashboard pane (started by Herdr)")
    commands.add_parser("open", help="open the dashboard over the active pane (plugin action)")
    commands.add_parser("open-tab", help="open the dashboard in a new tab (plugin action)")
    commands.add_parser("list", help="print the rows as JSON")
    parsed = parser.parse_args(args)
    if parsed.command == "dashboard":
        return _dashboard(environ)
    if parsed.command in ("open", "open-tab"):
        return _open(environ, tab=parsed.command == "open-tab")
    return _list(environ)


def _dashboard(environ):
    rt = make_runtime(environ)
    try:
        return terminal.run_dashboard(rt, environ.get("HERDR_PANE_ID"))
    except Exception:
        logfile.append(rt.paths.log, "dashboard error\n" + traceback.format_exc())
        return 1


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


def _list(environ):
    """Every row, the pane it runs in included (a Claude may call this from its own pane)."""
    try:
        rt = make_runtime(environ)
        found = inventory.build(rt, idle.Tracker.load(rt.paths.observed, rt.clock), None)
    except herdr_api.HerdrError as error:
        return fail(error)
    print(json.dumps([dataclasses.asdict(row) for row in found.rows], ensure_ascii=False, indent=2))
    return 0


def fail(message):
    print("agent-parking: %s" % message, file=sys.stderr)
    return 1
