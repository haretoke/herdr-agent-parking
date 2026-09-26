"""Compacting a Claude from the dashboard: ask it to prepare, read the focus it proposes,
then send `/compact <focus>`.

Outcome kinds: refused, blocked, prepared, prepare_failed, compacted, compact_failed.
"""

from collections import namedtuple

from . import config, ready, transcript

Outcome = namedtuple("Outcome", "kind message reply")


def prepare(rt, pane_id):
    """Send the preparation (`prepare_command`, or `prepare_prompt` when set)."""
    pane, refusal = ready.check(rt, pane_id, "compact")
    if refusal:
        return Outcome("refused", refusal, None)
    preparation = config.preparation(rt.settings)
    # The wait rides on the prompt request, so no status change can slip in between
    # (it may take minutes: the preparation can commit and push).
    rt.herdr.call("agent.prompt", {"target": pane_id, "text": preparation.first, "wait": {
        "until": ["idle", "done"], "timeout_ms": int(rt.settings["prepare_timeout_seconds"] * 1000)}})
    reply = transcript.preparation_reply(rt.rows_for(pane.session_id), preparation.first)
    return Outcome("prepared", "", reply)


REPORT_LINES = 8


def confirmation(reply):
    """The lines of the compact confirmation: the end of the preparation report (without
    the focus tag and the ready-to-type command) and the focus, which can be edited."""
    report = [line for line in reply.text.splitlines()
              if line.strip() and not transcript.FOCUS.search(line) and "/compact" not in line]
    focus = reply.focus or "(none, /compact alone)"
    return (["preparation report (end):"] + ["  " + line for line in report[-REPORT_LINES:]] +
            ["focus: " + focus, "Enter to compact, e to edit the focus, Esc to cancel"])
