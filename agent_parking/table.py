"""The dashboard's table: which columns fit the pane and how each row is drawn.

Narrow panes drop the lowest-priority columns first and give the space to the name
(decided with Fable, 2026-09-27; see DESIGN.md, "UI and keys").
"""


def columns(width):
    """The columns drawn at `width`: all from 78; without ver and rss at 64-77; ctx as
    tokens only and place without labels at 52-63; without idle and ctx under 52."""
    if width >= 78:
        return ("place", "name", "status", "idle", "ctx", "rss", "ver")
    if width >= 64:
        return ("place", "name", "status", "idle", "ctx")
    if width >= 52:
        return ("place_id", "name", "status", "idle", "ctx_short")
    return ("place_id", "name", "status")
