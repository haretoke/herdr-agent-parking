"""Resuming a parked session in its pane with `claude --resume <uuid>`.

Outcome kinds: refused, resumed, resume_pending, resume_failed.
"""

import shlex
from collections import namedtuple

from . import argv, display, herdr_api, records, times

Outcome = namedtuple("Outcome", "kind message record")


def agent_name(session_id):
    """The Herdr agent name for the resumed Claude (`[a-z][a-z0-9_-]{0,31}`)."""
    return "parking-" + session_id[:8]


def resume(rt, session_id):
    record = records.read(rt.paths.records, session_id)
    pane_id = record["pane_id"]
    pane = rt.herdr.pane(pane_id)
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
    rt.herdr.call("agent.start", {"name": agent_name(session_id), "kind": "claude", "pane_id": pane_id,
                                  "args": ["--resume", session_id] + flags,
                                  "timeout_ms": int(rt.settings["start_timeout_ms"])})
    return Outcome("resumed", "", record)


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
