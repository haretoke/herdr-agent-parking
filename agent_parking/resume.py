"""Resuming a parked session in its pane with `claude --resume <uuid>`.

Outcome kinds: refused, resumed, resume_pending, resume_failed.
"""

from collections import namedtuple

from . import argv, display, records, times

Outcome = namedtuple("Outcome", "kind message record")


def agent_name(session_id):
    """The Herdr agent name for the resumed Claude (`[a-z][a-z0-9_-]{0,31}`)."""
    return "parking-" + session_id[:8]


def resume(rt, session_id):
    record = records.read(rt.paths.records, session_id)
    pane_id = record["pane_id"]
    flags = argv.resume_flags(record.get("argv") or ["claude"]).flags
    rt.herdr.call("agent.start", {"name": agent_name(session_id), "kind": "claude", "pane_id": pane_id,
                                  "args": ["--resume", session_id] + flags,
                                  "timeout_ms": int(rt.settings["start_timeout_ms"])})
    return Outcome("resumed", "", record)


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
