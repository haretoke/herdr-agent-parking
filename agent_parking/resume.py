"""Resuming a parked session in its pane with `claude --resume <uuid>`.

Outcome kinds: refused, resumed, resume_pending, resume_failed.
"""

from collections import namedtuple

from . import argv, records

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
