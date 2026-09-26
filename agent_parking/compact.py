"""Compacting a Claude from the dashboard: ask it to prepare, read the focus it proposes,
then send `/compact <focus>`.

Outcome kinds: refused, blocked, prepared, prepare_failed, compacted, compact_failed.
"""

from collections import namedtuple

from . import config, ready

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
    return Outcome("prepared", "", None)
