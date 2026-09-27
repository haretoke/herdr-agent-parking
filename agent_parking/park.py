"""Parking: exit an idle Claude after recording how to bring it back."""

import os
import unicodedata
from collections import namedtuple

from . import (agents, config, display, herdr_api, inventory, layout, ready, records, runtime, screen, state, times,
               transcript)

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
    seen = agents.look(rt, pane_id)
    process, argv, env, command = seen.process, seen.argv, seen.env, seen.command
    background, refusal = _shown_background(pane, seen)
    if refusal:
        return Outcome("refused", refusal, None)
    own, remark, entry = agents.own_session(seen, pane)
    if entry and agents.not_idle(entry, ""):
        return Outcome("refused", agents.not_idle(entry, ""), None)
    session_id = background["sessionId"] if background else own
    runtime.remember_config_dir(rt, env)  # its transcript may live in its own config directory
    if not rt.has_transcript(session_id):
        # `claude --resume` finds no conversation for it (seen on the Mac): nothing to keep.
        return Outcome("refused", NO_CONVERSATION, None)
    tree = _tab_tree(rt, pane_id)
    record = {
        "schema_version": records.SCHEMA_VERSION, "session_id": session_id,
        "status": "parking", "pane_id": pane_id, "pane_id_history": [],
        "tab_id": pane.tab_id, "workspace_id": pane.workspace_id, "title": pane.title,
        # A pane alone in its tab closes with the tab, and `r` names the tab it opens after it.
        "tab_label": inventory.labels(rt, "tab.list", "tabs", "tab_id").get(pane.tab_id),
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
    unstarted = _end(rt, pane_id, session_id, background, command, env)
    if unstarted:
        return unstarted
    left, why = (_leave_view(rt, pane_id), None) if background else _wait_after_exit(rt, pane_id)
    if not left:
        record["status"] = "park_failed"
        records.write(rt.paths.records, record)
        return Outcome("park_failed", why or "Claude did not exit within %s s; the pane is left as it is "
                                             "(its record stays, so `r` works after a manual /exit)"
                       % rt.settings["exit_timeout_seconds"], record)
    mode, reason = ("keep", "") if keep else _close_or_keep(rt, pane_id)
    if mode == "close":
        rt.herdr.call("pane.close", {"pane_id": pane_id})
    else:
        rt.herdr.call("pane.rename", {"pane_id": pane_id, "label": label(rt.settings, record)})
    record.update(status="parked", parked_mode=mode)
    records.write(rt.paths.records, record)
    stopped = "stopped Claude's background session %s" % background["id"] if background else ""
    return Outcome("parked", "; ".join(part for part in (remark, stopped, reason) if part), record)


def _shown_background(pane, seen):
    """(Claude's entry for the session of its background the pane shows, or None; the reason
    not to park, or None). A `claude attach <id>` client, or a view Herdr names a background
    session for: /exit would leave the session running, `claude stop` ends it."""
    attached = agents.attached_to(seen.argv)
    entry = agents.running_background(seen.entries, pane.session_id, attached)
    if attached and entry is None:
        return None, agents.NOT_RUNNING % attached
    return entry, entry and agents.why_not_stop(entry, pane.title)


def _end(rt, pane_id, session_id, background, command, env):
    """End the Claude in the pane: `/exit`, or `claude stop` for a session of Claude's
    background (a view showing it goes back to the shell by itself, seen on the Mac). An
    Outcome when that cannot start, with the parking record dropped; else None."""
    if background:
        if rt.system.claude_stop(command, background["id"], env):
            return None
        records.discard_parking(rt.paths.records, session_id)
        return Outcome("park_failed", "`claude stop %s` failed; the session runs on as it was"
                       % background["id"], None)
    try:
        ready.empty_box(rt, pane_id)
        rt.herdr.call("agent.prompt", {"target": pane_id, "text": "/exit"})
    except herdr_api.HerdrError as error:
        records.discard_parking(rt.paths.records, session_id)
        if error.code == "agent_blocked":
            return Outcome("refused", "Claude is waiting at a dialog; answer it first (g)", None)
        raise
    return None


def _close_or_keep(rt, pane_id):
    """`on_park = close` closes the pane (the only pane of a tab takes the tab with it),
    except the last one of its workspace (that would close the workspace; spike 0-16) or one
    where something else than the shell took the foreground."""
    if rt.settings["on_park"] != "close":
        return "keep", ""
    if not _others_in_workspace(rt, pane_id):
        return "keep", "kept as the last pane of its workspace"
    if not herdr_api.shell_only(rt.herdr.process_info(pane_id)):
        return "keep", "kept: something other than the shell is running there"
    return "close", ""


def _others_in_workspace(rt, pane_id):
    """Its workspace has a pane besides this one and the dashboard's overlay (which closes
    with the dashboard). Read at the time: `S` parks one pane after another. False when
    Herdr cannot say."""
    try:
        panes = rt.herdr.panes()
    except herdr_api.HerdrError:
        return False
    workspace_id = next((p.workspace_id for p in panes if p.pane_id == pane_id), None)
    ignored = (pane_id, state.dashboard_pane(rt.environ))
    return workspace_id is not None and any(
        p.workspace_id == workspace_id and p.pane_id not in ignored for p in panes)


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


WORKTREE_QUESTION = ("Claude asks whether to keep its worktree, and Keep is not the selected answer; "
                     "answer it in the pane (g). The record stays, so `r` works once Claude has exited")


def _wait_after_exit(rt, pane_id):
    """`_wait_for_shell` after /exit, answering Claude's question in one of its worktrees with
    Keep, its default (seen in a container), and only when Keep is the selected answer:
    Remove would delete the branch. (True, None) once Claude has left, else (False, why)."""
    kept = False
    for attempt in range(int(rt.settings["exit_timeout_seconds"] / POLL_SECONDS) + 1):
        if attempt:
            rt.sleep(POLL_SECONDS)
        pane = rt.herdr.pane(pane_id)
        if pane is None or pane.agent is None:
            return True, None
        question = None if kept else screen.worktree_exit(rt.herdr.screen(pane_id))
        if question == "keep":
            rt.herdr.call("pane.send_keys", {"pane_id": pane_id, "keys": ["enter"]})
            kept = True
        elif question == "other":
            return False, WORKTREE_QUESTION
    return False, None


def _leave_view(rt, pane_id):
    """After `claude stop`, until the pane is back at the shell: a `claude attach` client
    exits by itself (seen on the Mac), while `claude agents` that showed the session may stay
    on its list; `/exit` leaves the list (in a session it shows, it goes to the list first)."""
    for _ in range(VIEW_EXITS):
        if _wait_for_shell(rt, pane_id, VIEW_SECONDS):
            return True
        if _claude_in_front(rt.herdr.process_info(pane_id)):
            rt.herdr.call("pane.send_input", {"pane_id": pane_id, "text": "/exit", "keys": ["Enter"]})
    return _wait_for_shell(rt, pane_id)


def _claude_in_front(info):
    """Whether Claude leads the pane's foreground: not the shell, nor a helper of its prompt
    (`mise`, `git`) while Herdr still says `claude` (seen on the Mac right after a stop)."""
    leader = inventory.claude_process(info) or {}
    started = os.path.basename((leader.get("argv") or [""])[0])
    return started == "claude" or leader.get("name") == "claude" or bool(
        inventory.VERSION.fullmatch(leader.get("name") or ""))


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
