"""Resuming a parked session in its pane with `claude --resume <uuid>`.

Outcome kinds: refused, resumed, resume_pending, resume_failed.
"""

import shlex
from collections import namedtuple

from . import argv, display, herdr_api, inventory, park, records, recreate, times

Outcome = namedtuple("Outcome", "kind message record")


def agent_name(session_id):
    """The Herdr agent name for the resumed Claude (`[a-z][a-z0-9_-]{0,31}`)."""
    return "parking-" + session_id[:8]


def resume(rt, session_id, new_workspace=False):
    """Resume the parked `session_id` in its pane, recreating the pane when it is gone
    (`new_workspace` allows a new workspace when its own is gone too)."""
    record = records.read(rt.paths.records, session_id)
    panes = rt.herdr.panes()
    [decision] = inventory.reconcile([record], panes)
    if decision.kind == "resumed":
        # Already running (a retry after a startup dialog, or resumed by hand): finish the
        # bookkeeping and never start a second process on the same transcript (spike 0-14).
        return _finish(rt, record, decision.pane_id, decision.restore_label_on)
    if decision.kind == "conflict":
        return Outcome("refused", "another Claude session runs in %s" % decision.pane_id, record)
    if decision.kind == "no_pane":
        placed = recreate.place(rt, record, panes, new_workspace=new_workspace)
        if placed.pane_id is None:
            return Outcome("refused", placed.message, record)
        record = records.with_pane(record, placed.pane_id)
        records.write(rt.paths.records, record)
    pane_id = record["pane_id"]
    pane = rt.herdr.pane(pane_id)
    if not herdr_api.shell_only(rt.herdr.process_info(pane_id)):
        return Outcome("refused", "something else is running in %s; look at it with g" % pane_id, record)
    if record.get("cwd") and pane is not None and pane.cwd != record["cwd"]:
        _type(rt, pane_id, "cd " + shlex.quote(record["cwd"]))
    if record.get("note"):
        # A secondary display; Claude's full-screen UI covers it (spike 0-12).
        lines = ["💤 " + line for line in record["note"].splitlines()]
        try:
            _type(rt, pane_id, "printf '%s\\n' " + " ".join(shlex.quote(line) for line in lines))
        except herdr_api.HerdrError:
            pass
    flags = argv.resume_flags(record.get("argv") or ["claude"]).flags
    try:
        start_ms = int(rt.settings["start_timeout_ms"])
        rt.herdr.call("agent.start", {"name": agent_name(session_id), "kind": "claude", "pane_id": pane_id,
                                      "args": ["--resume", session_id] + flags, "timeout_ms": start_ms},
                      timeout=start_ms / 1000 + herdr_api.WAIT_MARGIN_SECONDS)
    except herdr_api.HerdrError as error:
        if error.code == "timeout":
            record.update(status="resume_failed", error="%s\n%s" % (error, _tail(rt, pane_id)))
            records.write(rt.paths.records, record)
            return Outcome("resume_failed", record["error"], record)
        if error.code != "agent_not_ready":
            raise
        record["status"] = "resume_pending"
        records.write(rt.paths.records, record)
        return Outcome("resume_pending", "Claude is waiting at a dialog (trust, login); answer it in the "
                                         "pane (g), then press r again", record)
    started = rt.herdr.pane(pane_id)
    running = started.session_id if started is not None else None
    if running != session_id:
        record.update(status="resume_failed",
                      error="expected session %s in %s, found %s" % (session_id, pane_id, running))
        records.write(rt.paths.records, record)
        return Outcome("resume_failed", record["error"], record)
    outcome = _finish(rt, record, pane_id, pane_id)
    if rt.settings["send_note_as_prompt"] and record.get("note"):
        # Only once Claude is ready: a prompt typed over a dialog would land in it.
        rt.herdr.call("agent.wait", {"target": pane_id, "until": ["idle", "done"],
                                     "timeout_ms": int(rt.settings["start_timeout_ms"])},
                      timeout=rt.settings["start_timeout_ms"] / 1000 + herdr_api.WAIT_MARGIN_SECONDS)
        rt.herdr.call("agent.prompt", {"target": pane_id, "text": record["note"]})
    return outcome


def _finish(rt, record, running_in, restore_label_on):
    return Outcome("resumed", "", inventory.settle_resumed(rt, record, running_in, restore_label_on))


TAIL_LINES = 10


def _tail(rt, pane_id):
    """The pane's last lines, to show why a start failed (not stored beyond the record)."""
    try:
        read = rt.herdr.call("pane.read", {"pane_id": pane_id, "source": "recent", "lines": TAIL_LINES})
    except herdr_api.HerdrError:
        return ""
    text = (read.get("read") or {}).get("text") or ""
    return "\n".join(text.splitlines()[-TAIL_LINES:])


def _type(rt, pane_id, command):
    """Run `command` in the pane's shell (there is no socket `pane.run`)."""
    rt.herdr.call("pane.send_input", {"pane_id": pane_id, "text": command, "keys": ["Enter"]})


def confirmation(record, now):
    """The lines of the resume confirmation box for `record`."""
    parsed = argv.resume_flags(record.get("argv") or ["claude"])
    lines = ['resume %s "%s"' % (record.get("pane_id") or "(new pane)", record.get("title") or "")]
    parked_at = times.parse(record.get("parked_at"))
    if parked_at is not None:
        lines[0] += "  parked %s ago" % display.age((now - parked_at).total_seconds())
    lines.append("cwd   %s" % (record.get("cwd") or "?"))
    lines.append("claude --resume %s %s" % (record["session_id"][:8], " ".join(parsed.flags)))
    if parsed.dropped:
        lines.append("left out: " + ", ".join('"%s"' % token for token in parsed.dropped))
    if record.get("note"):
        lines.append("note:")
        lines.extend("  " + line for line in record["note"].splitlines())
    lines.append("Enter to resume, e to edit the note, Esc to cancel")
    return [line.rstrip() for line in lines]


def swap(rt, pane_id):
    """`R`: park the Claude in `pane_id` and resume it at once, so it restarts on the
    current `claude`. A park that does not complete does not resume.
    Returns (park Outcome, resume Outcome or None)."""
    parked = park.park(rt, pane_id, note=None)
    if parked.kind != "parked":
        return parked, None
    return parked, resume(rt, parked.record["session_id"])


def swap_question(running, current):
    """What to ask before a swap: nothing when a newer `claude` is there (the reason to swap),
    else whether to restart anyway."""
    if running is not None and current is not None and running != current:
        return None
    if running is None or current is None:
        return "the versions are unknown; restart this session anyway? (y/N)"
    return "this session already runs %s, the current claude; restart it anyway? (y/N)" % current
