"""Resuming a parked session in its pane with `claude --resume <uuid>`.

Outcome kinds: refused, resumed, resume_pending, resume_failed.
"""

import shlex
from collections import namedtuple

from . import argv, display, herdr_api, inventory, park, records, recreate, runtime, times

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
    runtime.remember_config_dir(rt, record.get("env"))  # where its transcript lives
    if not rt.has_transcript(session_id):
        # `claude --resume` would answer No conversation found (seen on the Mac).
        return Outcome("refused", "no conversation was ever saved for %s, so it cannot be resumed; "
                                  "x forgets the record" % session_id[:8], record)
    if decision.kind == "no_pane":
        placed = recreate.place(rt, record, panes, new_workspace=new_workspace)
        if placed.pane_id is None:
            return Outcome("refused", placed.message, record)
        record = records.with_pane(record, placed.pane_id)
        records.write(rt.paths.records, record)
        _wait_for_new_shell(rt, placed.pane_id)
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
    env = record.get("env") or {}
    if env:
        # The variables that picked its account (claude-alt style wrappers) must be set
        # again, and agent.start takes no environment: type the command with `env` first.
        _type(rt, pane_id, " ".join(
            ["env"] + [shlex.quote("%s=%s" % item) for item in sorted(env.items())]
            + [shlex.quote(rt.settings["claude_command"]), "--resume", shlex.quote(session_id)]
            + [shlex.quote(flag) for flag in flags]))
    else:
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
            return _pending(rt, record)
    running = _running_session(rt, pane_id)
    if running is AT_DIALOG:
        return _pending(rt, record)
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


def _pending(rt, record):
    """Claude waits at a dialog: the record says so, and `r` again finishes once it is answered."""
    record["status"] = "resume_pending"
    records.write(rt.paths.records, record)
    return Outcome("resume_pending", "Claude is waiting at a dialog (trust, login); answer it in the "
                                     "pane (g), then press r again", record)


SESSION_POLL_SECONDS = 0.5
AT_DIALOG = object()


def _running_session(rt, pane_id):
    """The session Herdr sees in the pane after the start. Herdr can detect it a moment
    after `agent.start` returns (seen on the Mac), so no session yet is asked again until
    the start timeout; another session is an answer at once. AT_DIALOG when Claude is
    `blocked` without a session: `agent.start` returns at the trust dialog (seen on the
    Mac) instead of failing with `agent_not_ready`."""
    limit = rt.settings["start_timeout_ms"] / 1000
    waited = 0.0
    while True:
        pane = rt.herdr.pane(pane_id)
        running = pane.session_id if pane is not None else None
        if running is None and pane is not None and pane.agent_status == "blocked":
            return AT_DIALOG
        if running is not None or waited >= limit:
            return running
        rt.sleep(SESSION_POLL_SECONDS)
        waited += SESSION_POLL_SECONDS


NEW_SHELL_SECONDS = 10


def _wait_for_new_shell(rt, pane_id):
    """A pane just created runs its shell's startup for a moment (seen on the Mac: the
    foreground was not the shell yet); wait until the shell alone is there, at most
    NEW_SHELL_SECONDS. The check that follows refuses when it never is."""
    waited = 0.0
    while waited < NEW_SHELL_SECONDS and not herdr_api.shell_only(rt.herdr.process_info(pane_id)):
        rt.sleep(SESSION_POLL_SECONDS)
        waited += SESSION_POLL_SECONDS


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
    env = record.get("env") or {}
    if inventory.account_name(env):
        lines.append("account %s" % inventory.account_name(env))
    prefix = "env %s " % " ".join("%s=%s" % item for item in sorted(env.items())) if env else ""
    lines.append("%sclaude --resume %s %s" % (prefix, record["session_id"][:8], " ".join(parsed.flags)))
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
    parked = park.park(rt, pane_id, note=None, keep=True)
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
