"""Parking: exit an idle Claude after recording how to bring it back."""

from collections import namedtuple

# kind: refused, parked, park_failed
Outcome = namedtuple("Outcome", "kind message record")

PARKABLE = ("idle", "done")


def park(rt, pane_id, note):
    pane = rt.herdr.pane(pane_id)
    if pane is None or pane.agent != "claude":
        return Outcome("refused", "no Claude in %s" % pane_id, None)
    if pane.agent_status not in PARKABLE:
        return Outcome("refused", "Claude is %s; only idle or done sessions park" % pane.agent_status, None)
    return Outcome("parked", "", None)
