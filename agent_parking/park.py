"""Parking: exit an idle Claude after recording how to bring it back."""

from collections import namedtuple

from . import herdr_api, inventory, layout, records, screen, times, transcript

# kind: refused, parked, park_failed
Outcome = namedtuple("Outcome", "kind message record")

PARKABLE = ("idle", "done")
POLL_SECONDS = 0.5


def park(rt, pane_id, note):
    pane = rt.herdr.pane(pane_id)
    if pane is None or pane.agent != "claude":
        return Outcome("refused", "no Claude in %s" % pane_id, None)
    if pane.agent_status not in PARKABLE:
        return Outcome("refused", "Claude is %s; only idle or done sessions park" % pane.agent_status, None)
    if not pane.session_id:
        return Outcome("refused", "Herdr does not know this Claude's session; run "
                                  "`herdr integration install claude` and restart it", None)
    if screen.input_box(rt.herdr.screen(pane_id)) != "empty":
        return Outcome("refused", "a draft is in Claude's input box; clear it first (g, then Ctrl+C)", None)
    process = inventory.claude_process(rt.herdr.process_info(pane_id)) or {}
    tree = _tab_tree(rt, pane_id)
    record = {
        "schema_version": records.SCHEMA_VERSION, "session_id": pane.session_id,
        "status": "parking", "pane_id": pane_id, "pane_id_history": [],
        "tab_id": pane.tab_id, "workspace_id": pane.workspace_id, "title": pane.title,
        "cwd": process.get("cwd") or pane.cwd,
        "argv": inventory.argv_of(process, rt.system) if process else [],
        "claude_version": inventory.running_version(process, rt.system) if process else None,
        "label_before": pane.label, "layout_hint": layout.hint(tree, pane_id),
        "context_at_park": _context(rt, pane.session_id),
        "parked_at": times.iso(rt.clock()),
        "note": note if note and note.strip() else None,
    }
    # Herdr forgets the session id once Claude exits (spike 0-2): write it down first.
    records.start_parking(rt.paths.records, record)
    try:
        rt.herdr.call("agent.prompt", {"target": pane_id, "text": "/exit"})
    except herdr_api.HerdrError as error:
        records.discard_parking(rt.paths.records, pane.session_id)
        if error.code == "agent_blocked":
            return Outcome("refused", "Claude is waiting at a dialog; answer it first (g)", None)
        raise
    if not _wait_for_shell(rt, pane_id):
        record["status"] = "park_failed"
        records.write(rt.paths.records, record)
        return Outcome("park_failed", "Claude did not exit within %s s; the pane is left as it is "
                                      "(its record stays, so `r` works after a manual /exit)"
                       % rt.settings["exit_timeout_seconds"], record)
    mode, reason = _close_or_keep(rt, pane_id, tree)
    if mode == "close":
        rt.herdr.call("pane.close", {"pane_id": pane_id})
    else:
        rt.herdr.call("pane.rename", {"pane_id": pane_id, "label": _label(rt.settings, record)})
    record.update(status="parked", parked_mode=mode)
    records.write(rt.paths.records, record)
    return Outcome("parked", reason, record)


def _close_or_keep(rt, pane_id, tree):
    """`on_park = close` closes the pane, except the last one of its tab (that would close
    the tab; spike 0-16) or one where something else than the shell took the foreground."""
    if rt.settings["on_park"] != "close":
        return "keep", ""
    if not isinstance(tree, dict) or tree.get("type") != "split":
        return "keep", "kept: the last pane of its tab is never closed"
    if not herdr_api.shell_only(rt.herdr.process_info(pane_id)):
        return "keep", "kept: something other than the shell is running there"
    return "close", ""


def _tab_tree(rt, pane_id):
    """The split tree of the pane's tab (`layout.export`), or None when Herdr cannot say."""
    try:
        exported = rt.herdr.call("layout.export", {"pane_id": pane_id})
    except herdr_api.HerdrError:
        return None
    return exported.get("layout", exported).get("root")


def _label(settings, record):
    """The parked pane's label from `parked_label_format`."""
    return settings["parked_label_format"].format(title=record.get("title") or "",
                                                  short_id=record["session_id"][:8])


def _context(rt, session_id):
    summary = rt.summary_for(session_id) or transcript.EMPTY
    window = transcript.window_size(summary.model, session_id, rt.settings["context_window_by_model"],
                                    rt.statusline_windows)
    return {"tokens": summary.tokens, "percent": transcript.percent(summary.tokens, window),
            "compacted": summary.compacted}


def _wait_for_shell(rt, pane_id):
    """Poll until Claude has left `pane_id` (about 4 s in spike 0-2)."""
    for attempt in range(int(rt.settings["exit_timeout_seconds"] / POLL_SECONDS) + 1):
        if attempt:
            rt.sleep(POLL_SECONDS)
        pane = rt.herdr.pane(pane_id)
        if pane is None or pane.agent is None:
            return True
    return False


LOST_WORK = ("Parking ends the process: background tasks, running subagents and MCP server "
             "state are lost and do not come back on resume.")


def confirmation(row):
    """The lines of the park confirmation box for `row`."""
    title = '"%s"' % row.name if row.name else ""
    return [("park %s %s" % (row.pane_id, title)).rstrip(), LOST_WORK,
            "note (empty for none; a blank line or Ctrl-D ends it):"]
