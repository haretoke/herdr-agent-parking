"""The plugin's commands: `dashboard` (the pane process), `open` and `open-tab` (the
plugin actions that open it), `list` (the rows as JSON for scripts), and `park`,
`compact` and `resume`, the dashboard's procedures without the dashboard."""

import argparse
import dataclasses
import json
import sys
import traceback
from datetime import datetime, timezone

from . import (compact, config, display, herdr_api, idle, inventory, logfile, park, presence, records, recreate, resume,
               runtime, state, system, terminal, transcript)

DONE = ("parked", "compacted", "resumed")


def _now():
    return datetime.now(timezone.utc)


def make_runtime(environ):
    """The Runtime of a plugin process: Herdr over `HERDR_SOCKET_PATH`, this machine's
    processes, the plugin's state directory, and transcripts read through a cache."""
    log = state.state_dir(environ) / "dashboard.log"
    settings = config.load(state.config_dir(environ) / "config.json", lambda line: logfile.append(log, line))
    # The plugin's own, then those of Claudes started with another CLAUDE_CONFIG_DIR.
    config_dirs = [state.claude_config_dir(environ, settings)]
    summaries = transcript.Cache(transcript.load)

    def find(session_id):
        return transcript.find_any(config_dirs, session_id)

    def rows_for(session_id):
        """The tail of the session's transcript (the compact flow reads Claude's replies)."""
        path = find(session_id)
        try:
            return transcript.read_tail(path) if path is not None else []
        except OSError:
            return []

    paths = state.paths(environ, settings)
    return runtime.Runtime(
        herdr=herdr_api.Herdr.from_environ(environ), system=system.System(),
        paths=paths, settings=settings, clock=_now, environ=environ,
        summary_for=lambda session_id: summaries.get(find(session_id)),
        rows_for=rows_for,
        has_transcript=lambda session_id: find(session_id) is not None,
        statusline_windows=transcript.statusline_windows(paths.windows),
        claude_config_dirs=config_dirs)


def main(args, environ):
    parser = argparse.ArgumentParser(prog="agent-parking")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("dashboard", help="run the dashboard pane (started by Herdr)")
    commands.add_parser("open", help="open the dashboard over the active pane (plugin action)")
    commands.add_parser("open-tab", help="open the dashboard in a new tab (plugin action)")
    commands.add_parser("list", help="print the rows as JSON")
    parking = commands.add_parser("park", help="park the Claude in a pane")
    parking.add_argument("pane_id")
    parking.add_argument("--note", default=None)
    compacting = commands.add_parser("compact", help="prepare, print the report, then compact the Claude in a pane")
    compacting.add_argument("pane_id")
    compacting.add_argument("--focus", default=None, help="compact with this focus instead of the proposed one")
    resuming = commands.add_parser("resume", help="resume a parked session by its UUID")
    resuming.add_argument("session_id")
    resuming.add_argument("--new-workspace", action="store_true",
                          help="open a new workspace when the session's own is gone")
    parsed = parser.parse_args(args)
    if parsed.command == "dashboard":
        return _dashboard(environ)
    if parsed.command in ("open", "open-tab"):
        return _open(environ, tab=parsed.command == "open-tab")
    if parsed.command == "park":
        return _procedure(environ, lambda rt: park.park(rt, parsed.pane_id, parsed.note), parsed.pane_id)
    if parsed.command == "compact":
        return _procedure(environ, lambda rt: _compact(rt, parsed.pane_id, parsed.focus), parsed.pane_id)
    if parsed.command == "resume":
        return _procedure(environ, lambda rt: resume.resume(rt, parsed.session_id, new_workspace=parsed.new_workspace),
                          parsed.session_id)
    return _list(environ)


def _compact(rt, pane_id, focus):
    """The dashboard's `c` without its confirmation: the report and the focus are printed,
    then `/compact` goes with the proposed focus, or `--focus` when given."""
    prepared = compact.prepare(rt, pane_id)
    if prepared.kind != "prepared":
        return prepared
    reply = prepared.reply if focus is None else prepared.reply._replace(focus=focus)
    for line in ([prepared.message] if prepared.message else []) + compact.confirmation(reply)[:-1]:
        print(line)
    return compact.run(rt, pane_id, reply.focus)


def _procedure(environ, run, subject):
    """Run a flow and report its outcome: printed when it did what was asked, else on
    stderr with exit 1."""
    try:
        outcome = run(make_runtime(environ))
    except (herdr_api.HerdrError, records.Refused, OSError) as error:
        return fail(error)
    text = display.said(outcome, subject)
    if outcome.kind not in DONE:
        if outcome.message == recreate.NEEDS_WORKSPACE:
            text += " (run again with --new-workspace)"
        return fail(text)
    print(text)
    return 0


def _dashboard(environ):
    rt = make_runtime(environ)
    try:
        return terminal.run_dashboard(rt, environ.get("HERDR_PANE_ID"))
    except Exception:
        logfile.append(rt.paths.log, "dashboard error\n" + traceback.format_exc())
        return 1


def _open(environ, tab):
    """The `open` action: the dashboard over the active pane (overlay); `open-tab`: in a
    new tab of the current workspace, for people who keep it open. One dashboard at a
    time: one kept in a tab is focused, an overlay left open elsewhere is closed and
    opened again here."""
    try:
        rt = make_runtime(environ)
        running = presence.current(rt.paths.dashboard)
        if running is not None and _pane_exists(rt, running["pane_id"]):
            if running.get("placement") == "tab":
                rt.herdr.call("plugin.pane.focus", {"pane_id": running["pane_id"]})
                return 0
            rt.herdr.call("plugin.pane.close", {"pane_id": running["pane_id"]})
    except herdr_api.HerdrError as error:
        return fail(error)
    placement = "tab" if tab else "overlay"
    # The dashboard records how it was opened, so the next `open` knows whether to move it.
    params = {"plugin_id": state.PLUGIN_ID, "entrypoint": "dashboard", "placement": placement, "focus": True,
              "env": {"AGENT_PARKING_PLACEMENT": placement}}
    if tab and environ.get("HERDR_WORKSPACE_ID"):
        params["workspace_id"] = environ["HERDR_WORKSPACE_ID"]
    try:
        rt.herdr.call("plugin.pane.open", params)
    except herdr_api.HerdrError as error:
        return fail(error)
    return 0


def _pane_exists(rt, pane_id):
    try:
        return rt.herdr.pane(pane_id) is not None
    except herdr_api.HerdrError:
        return False


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
