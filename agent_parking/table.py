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


PARKED_MARK = "💤"


def _ids(row):
    """`w8/t3/p36` from the workspace, tab and pane ids (`w8:t3`, `w8:p36`)."""
    if not row.pane_id:
        return "(no pane)"
    parts = [row.workspace_id] + [(i or "").split(":")[-1] for i in (row.tab_id, row.pane_id)]
    return "/".join(p for p in parts if p)


def _memory(kib):
    if kib is None:
        return ""
    if kib < 1024 * 1024:
        return "%dM" % round(kib / 1024)
    return "%.1fG" % (kib / 1024 / 1024)


def _short_ctx(ctx):
    """`37k 18%` -> `37k`, `compacted 2h` -> `cmp 2h`."""
    if ctx.startswith("compacted"):
        return "cmp" + ctx[len("compacted"):]
    return ctx.split(" ")[0]


def cells(row, idle):
    """The text of every column for `row` (`idle` comes from the idle tracking)."""
    ids = _ids(row)
    if row.record is not None:
        place = place_id = ids + " " + PARKED_MARK
    else:
        label = row.label or row.tab_label or row.workspace_label
        place, place_id = (ids + " " + label if label else ids), ids
    return {"place": place, "place_id": place_id, "name": row.name or "", "status": row.status or "",
            "idle": idle, "ctx": row.ctx, "ctx_short": _short_ctx(row.ctx),
            "rss": "—" if row.record is not None else _memory(row.rss_kb),
            "ver": (row.version or "") + (" old" if row.old else "")}
