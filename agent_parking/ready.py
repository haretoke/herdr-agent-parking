"""Whether a Claude pane can take a park or a compact now."""

from . import screen

READY_STATUSES = ("idle", "done")


def check(rt, pane_id, action):
    """(pane, None) when `pane_id` holds an idle or done Claude with a known session and an
    empty input box; else (pane or None, the reason `action` is refused)."""
    pane = rt.herdr.pane(pane_id)
    if pane is None or pane.agent != "claude":
        return pane, "no Claude in %s" % pane_id
    if pane.agent_status not in READY_STATUSES:
        return pane, "Claude is %s; only idle or done sessions %s" % (pane.agent_status, action)
    if not pane.session_id:
        return pane, ("Herdr does not know this Claude's session; run "
                      "`herdr integration install claude` and restart it")
    box = screen.input_box(rt.herdr.screen(pane_id))
    if box == "draft":
        return pane, "a draft is in Claude's input box; clear it first (g, then Ctrl+C)"
    if box != "empty":
        return pane, "could not find Claude's input box on its screen; look at the pane first (g)"
    return pane, None
