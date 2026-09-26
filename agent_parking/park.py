"""Parking: exit an idle Claude after recording how to bring it back."""

from collections import namedtuple

from . import screen

# kind: refused, parked, park_failed
Outcome = namedtuple("Outcome", "kind message record")

PARKABLE = ("idle", "done")


def park(rt, pane_id, note):
    pane = rt.herdr.pane(pane_id)
    if pane is None or pane.agent != "claude":
        return Outcome("refused", "no Claude in %s" % pane_id, None)
    if pane.agent_status not in PARKABLE:
        return Outcome("refused", "Claude is %s; only idle or done sessions park" % pane.agent_status, None)
    if not pane.session_id:
        return Outcome("refused", "Herdr does not know this Claude's session; run "
                                  "`herdr integration install claude` and restart it", None)
    if screen.input_box(rt.herdr.screen(pane_id)) != "empty":
        return Outcome("refused", "a draft is in Claude's input box; clear it first (g, then Ctrl+C)", None)
    return Outcome("parked", "", None)


LOST_WORK = ("Parking ends the process: background tasks, running subagents and MCP server "
             "state are lost and do not come back on resume.")


def confirmation(row):
    """The lines of the park confirmation box for `row`."""
    title = '"%s"' % row.name if row.name else ""
    return [("park %s %s" % (row.pane_id, title)).rstrip(), LOST_WORK,
            "note (empty for none; a blank line or Ctrl-D ends it):"]
