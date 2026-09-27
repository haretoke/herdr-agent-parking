"""Parking: exit an idle Claude after recording how to bring it back."""

import unicodedata
from collections import namedtuple

from . import agents, config, display, herdr_api, inventory, layout, ready, records, runtime, state, times, transcript

# kind: refused, parked, park_failed
Outcome = namedtuple("Outcome", "kind message record")

PARKABLE = ready.READY_STATUSES
NO_CONVERSATION = "this Claude has no conversation yet, so there is nothing to resume; exit it with /exit instead"
POLL_SECONDS = 0.5
VIEW_SECONDS = 5
VIEW_EXITS = 2


def park(rt, pane_id, note, keep=False):
    """Park the Claude in `pane_id`; `keep` leaves the pane whatever `on_park` says (a swap
    resumes in it at once)."""
    pane, refusal = ready.check(rt, pane_id, "park")
    if refusal:
        return Outcome("refused", refusal, None)
    process = inventory.claude_process(rt.herdr.process_info(pane_id)) or {}
    argv = inventory.argv_of(process, rt.system) if process else []
    env = inventory.account_env(process, rt.system, rt.settings)
    command = inventory.claude_executable(argv[0] if argv else None, rt.settings, rt.system, rt.environ)
    # A session of Claude's background shown here (`claude attach <id>`, or a view Herdr
    # names it for): /exit would leave it running, `claude stop` ends it.
    attached = agents.attached_to(argv)
    background = agents.running_background(rt.system.claude_agents(command, env), pane.session_id, attached)
    if attached and background is None:
        return Outcome("refused", agents.NOT_RUNNING % attached, None)
    refusal = background and agents.why_not_stop(background, pane.title)
    if refusal:
        return Outcome("refused", refusal, None)
    session_id = background["sessionId"] if background else pane.session_id
    runtime.remember_config_dir(rt, env)  # its transcript may live in its own config directory
    if not rt.has_transcript(session_id):
        # `claude --resume` finds no conversation for it (seen on the Mac): nothing to keep.
        return Outcome("refused", NO_CONVERSATION, None)
    tree = _tab_tree(rt, pane_id)
    record = {
        "schema_version": records.SCHEMA_VERSION, "session_id": session_id,
        "status": "parking", "pane_id": pane_id, "pane_id_history": [],
        "tab_id": pane.tab_id, "workspace_id": pane.workspace_id, "title": pane.title,
        "cwd": (background or {}).get("cwd") or process.get("cwd") or pane.cwd,
        # A view's own arguments (`agents`, `attach <id>`) are no flags of the session.
        "argv": argv[:1] if background else argv,
        "env": env,
        "claude_version": inventory.running_version(process, rt.system) if process else None,
        "label_before": _label_before(rt, pane), "layout_hint": layout.hint(tree, pane_id),
        "context_at_park": _context(rt, session_id),
        "parked_at": times.iso(rt.clock()),
        "note": note if note and note.strip() else None,
    }
    if background:
        record["background_id"] = background["id"]
    # Herdr forgets the session id once Claude exits (spike 0-2): write it down first.
    records.start_parking(rt.paths.records, record)
    if background:
        stopped = "stopped Claude's background session %s" % background["id"]
        # A view showing it goes back to the shell by itself (seen on the Mac).
        if not rt.system.claude_stop(command, background["id"], env):
            records.discard_parking(rt.paths.records, session_id)
            return Outcome("park_failed", "`claude stop %s` failed; the session runs on as it was"
                           % background["id"], None)
    else:
        stopped = ""
        try:
            rt.herdr.call("agent.prompt", {"target": pane_id, "text": "/exit"})
        except herdr_api.HerdrError as error:
            records.discard_parking(rt.paths.records, session_id)
            if error.code == "agent_blocked":
                return Outcome("refused", "Claude is waiting at a dialog; answer it first (g)", None)
            raise
    if not (_leave_view(rt, pane_id) if background else _wait_for_shell(rt, pane_id)):
        record["status"] = "park_failed"
        records.write(rt.paths.records, record)
        return Outcome("park_failed", "Claude did not exit within %s s; the pane is left as it is "
                                      "(its record stays, so `r` works after a manual /exit)"
                       % rt.settings["exit_timeout_seconds"], record)
    mode, reason = ("keep", "") if keep else _close_or_keep(rt, pane_id, tree)
    if mode == "close":
        rt.herdr.call("pane.close", {"pane_id": pane_id})
    else:
        rt.herdr.call("pane.rename", {"pane_id": pane_id, "label": label(rt.settings, record)})
    record.update(status="parked", parked_mode=mode)
    records.write(rt.paths.records, record)
    return Outcome("parked", "; ".join(part for part in (stopped, reason) if part), record)


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


def _label_before(rt, pane):
    """The pane's own label. When an earlier record of this session is still there and the
    pane still shows the label that park gave it (the session was resumed by hand), the
    earlier `label_before` is the real one."""
    earlier = records.read(rt.paths.records, pane.session_id)
    if earlier is not None and pane.label and pane.label == label(rt.settings, earlier):
        return earlier.get("label_before")
    return pane.label


def _tab_tree(rt, pane_id):
    """The split tree of the pane's tab (`layout.export`) as it is without the dashboard's
    own overlay, or None when Herdr cannot say."""
    try:
        exported = rt.herdr.call("layout.export", {"pane_id": pane_id})
    except herdr_api.HerdrError:
        return None
    return layout.without(exported.get("layout", exported).get("root"), state.dashboard_pane(rt.environ))


LABEL_LIMIT = 80


def label(settings, record):
    """The parked pane's label from `parked_label_format` (`{title}`, `{short_id}`), without
    control characters and at most 80 characters; a broken format uses the default."""
    fields = {"title": record.get("title") or "", "short_id": record["session_id"][:8]}
    try:
        text = settings["parked_label_format"].format(**fields)
    except (KeyError, IndexError, ValueError):
        text = config.DEFAULTS["parked_label_format"].format(**fields)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cc")
    return text[:LABEL_LIMIT]


def _context(rt, session_id):
    summary = rt.summary_for(session_id) or transcript.EMPTY
    window = transcript.window_size(summary.model, session_id, rt.settings["context_window_by_model"],
                                    rt.statusline_windows)
    return {"tokens": summary.tokens, "percent": transcript.percent(summary.tokens, window),
            "compacted": summary.compacted}


def _leave_view(rt, pane_id):
    """After `claude stop`, until the pane is back at the shell: a `claude attach` client
    exits by itself (seen on the Mac), while `claude agents` that showed the session may stay
    on its list; `/exit` leaves the list (in a session it shows, it goes to the list first)."""
    for _ in range(VIEW_EXITS):
        if _wait_for_shell(rt, pane_id, VIEW_SECONDS):
            return True
        rt.herdr.call("pane.send_input", {"pane_id": pane_id, "text": "/exit", "keys": ["Enter"]})
    return _wait_for_shell(rt, pane_id)


def _wait_for_shell(rt, pane_id, seconds=None):
    """Poll until Claude has left `pane_id` (about 4 s in spike 0-2), at most `seconds`
    (`exit_timeout_seconds`)."""
    seconds = rt.settings["exit_timeout_seconds"] if seconds is None else seconds
    for attempt in range(int(seconds / POLL_SECONDS) + 1):
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


def bulk_targets(rows, entries, now, minutes):
    """The rows `S` parks: idle or done for at least `minutes` (a `≥` lower bound counts),
    and the others with the reason they are left out."""
    targets, skipped = [], []
    for row in rows:
        entry = entries.get(row.pane_id)
        if row.status not in PARKABLE:
            skipped.append((row, row.status or "unknown"))
        elif not row.has_transcript:
            skipped.append((row, "no conversation yet"))
        elif entry is None:
            skipped.append((row, "idle time unknown"))
        elif (now - entry.since).total_seconds() < minutes * 60:
            skipped.append((row, "%s %s" % (row.status, display.age((now - entry.since).total_seconds()))))
        else:
            targets.append(row)
    return targets, skipped


def bulk_park(pane_ids, park_one):
    """Park each pane in turn with `park_one(pane_id)`; one failure does not stop the rest.
    Returns `[(pane_id, Outcome)]`."""
    results = []
    for pane_id in pane_ids:
        try:
            outcome = park_one(pane_id)
        except (herdr_api.HerdrError, records.Refused, OSError) as error:
            outcome = Outcome("park_failed", str(error), None)
        results.append((pane_id, outcome))
    return results
