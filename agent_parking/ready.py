"""Whether a Claude pane can take a park or a compact now."""

from . import screen

READY_STATUSES = ("idle", "done")
# Claude's agent view titles its terminal "6 awaiting input · claude agents". Herdr keeps
# the id of the session the pane showed before (seen in a container and on the Mac).
AGENT_VIEW = ("this pane shows Claude's agent view (claude agents), not a session; "
              "open the session there, or exit the view with /exit by hand")


def check(rt, pane_id, action):
    """(pane, None) when `pane_id` holds an idle or done Claude with a known session and an
    empty input box; else (pane or None, the reason `action` is refused)."""
    pane = rt.herdr.pane(pane_id)
    if pane is None or pane.agent != "claude":
        return pane, "no Claude in %s" % pane_id
    if (pane.title or "").endswith("claude agents"):
        return pane, AGENT_VIEW
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


def empty_box(rt, pane_id):
    """Empty Claude's input box before a command is typed there. A blank left in it does not
    show on the screen (a typed space, seen on the Mac), so `check` reads the box as empty,
    and the command after it goes as a message (Claude got ' /exit' in a container). Ctrl+U
    empties the line and does nothing to an empty one (seen on the Mac)."""
    rt.herdr.call("pane.send_keys", {"pane_id": pane_id, "keys": ["ctrl+u"]})
