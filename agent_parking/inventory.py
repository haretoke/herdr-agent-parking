"""The dashboard's rows: every Claude pane of this Herdr server with what the plugin
knows about it (process, memory, version, context, park record)."""


def claude_panes(panes, own_pane_id):
    """The panes Herdr recognizes as Claude, without the dashboard's own pane."""
    return [p for p in panes if p.agent == "claude" and p.pane_id != own_pane_id]
