"""The dashboard's table: which columns fit the pane and how each row is drawn.

Narrow panes drop the lowest-priority columns first and give the space to the name
(decided with Fable, 2026-09-27; see DESIGN.md, "UI and keys").
"""

from collections import namedtuple

from . import display, inventory


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


MARK_WIDTH = 2  # the selection mark `▶ `
MIN_NAME = 12
FIXED = {"place": 13, "place_id": 11, "status": 8, "idle": 6, "ctx": 13, "ctx_short": 7, "rss": 5, "ver": 11}


def widths(cols, width):
    """Each column's width at `width`: the fixed ones, and the rest for the name (at least
    `MIN_NAME`, even when that makes the line too wide; it is cut when drawn)."""
    fixed = {c: FIXED[c] for c in cols if c != "name"}
    rest = width - MARK_WIDTH - sum(fixed.values()) - (len(cols) - 1)
    return dict(fixed, name=max(MIN_NAME, rest))


def _pad(text, columns):
    text = display.cell(text, columns)
    return text + " " * (columns - display.width(text))


def line(cells, width, selected, own_tab=False):
    """One row of the table at `width`, cut to the width when the name's minimum overflows
    it; a row of the tab the dashboard runs in carries `●` before its place."""
    cols = columns(width)
    sizes = widths(cols, width)
    shown = dict(cells)
    if "ver" not in cols:
        shown["status"] += cells["old"]
    if own_tab:
        shown["place"], shown["place_id"] = OWN_MARK + cells["place"], OWN_MARK + cells["place_id"]
    text = ("▶ " if selected else "  ") + " ".join(_pad(shown[c], sizes[c]) for c in cols)
    return display.cell(text.rstrip(), width)


TITLES = {"place": "place", "place_id": "place", "name": "name", "status": "status", "idle": "idle",
          "ctx": "ctx", "ctx_short": "ctx", "rss": "rss", "ver": "ver", "old": ""}


def header(width):
    """The column titles, aligned with `line`."""
    return line(TITLES, width, selected=False)


def detail(cells, note, width):
    """The line under the selected row: what the columns at `width` leave out, and the
    note's first line; empty when there is nothing to add."""
    cols = columns(width)
    label = cells["place"][len(cells["place_id"]):].strip()
    parts = []
    if "place" not in cols and label:
        parts.append(label)
    if "idle" not in cols and cells["idle"]:
        parts.append("idle " + cells["idle"])
    parts.extend(cells[c] for c in ("ctx", "rss", "ver") if c not in cols and cells[c] not in ("", "—"))
    if cells.get("account"):
        parts.append("account " + cells["account"])
    if note:
        parts.append('"%s"' % note.splitlines()[0])
    return display.cell("    ↳ " + " · ".join(parts), width) if parts else ""


PARKED_MARK = "💤"
OWN_MARK = "●"  # the workspace and tab the dashboard runs in


NO_PANE = "no pane"  # the place of a parked record whose pane is gone


def _ids(row, with_workspace):
    """`w8/t3/p36` from the workspace, tab and pane ids (`w8:t3`, `w8:p36`), or `t3/p36`
    without the workspace (the group header names it)."""
    if not row.pane_id:
        return "(%s)" % NO_PANE if with_workspace else NO_PANE
    parts = [(i or "").split(":")[-1] for i in (row.tab_id, row.pane_id)]
    if with_workspace:
        parts.insert(0, row.workspace_id)
    return "/".join(p for p in parts if p)


def memory(kib):
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


def cells(row):
    """The text of every column for `row`."""
    ids = _ids(row, with_workspace=False)
    if row.record is not None:
        place = place_id = ids + " " + PARKED_MARK
    else:
        label = row.label or row.tab_label
        place, place_id = (ids + " " + label if label else ids), ids
    return {"place": place, "place_id": place_id, "place_full": _ids(row, with_workspace=True),
            "name": row.name or "", "status": row.status or "",
            "idle": row.idle, "ctx": row.ctx, "ctx_short": _short_ctx(row.ctx),
            "rss": "—" if row.record is not None else memory(row.rss_kb),
            "ver": (row.version or "") + (" old" if row.old else ""), "old": "!" if row.old else "",
            "account": inventory.account_name(row.env)}


# The rows of one workspace, under one header line. `workspace_id` is None for parked
# records that no longer say where they were.
Group = namedtuple("Group", "workspace_id label rows")


def groups(rows):
    """The rows grouped by workspace, the groups in the order their first row appears
    (live rows come first, so a workspace with only parked sessions sinks), each named by
    the first label any of its rows knows."""
    found = {}
    for row in rows:
        group = found.get(row.workspace_id) or Group(row.workspace_id, None, [])
        if row.workspace_id is not None and not group.label and row.workspace_label:
            group = group._replace(label=row.workspace_label)
        group.rows.append(row)
        found[row.workspace_id] = group
    return list(found.values())


def group_header(group, width, own):
    """` ── shop-api (w8) · 1 claude · 1 parked ─────` cut or filled to `width`; the
    workspace the dashboard runs in is marked with `●`."""
    if group.workspace_id is None:
        name = "(no workspace)"
    elif group.label:
        name = "%s (%s)" % (group.label, group.workspace_id)
    else:
        name = group.workspace_id
    parts = [name]
    live = sum(1 for row in group.rows if row.record is None)
    parked = len(group.rows) - live
    if live:
        parts.append("%d claude" % live)
    if parked:
        parts.append("%d parked" % parked)
    text = display.cell(" ── " + (OWN_MARK + " " if own else "") + " · ".join(parts) + " ", width)
    return text + "─" * (width - display.width(text))  # filled after the cut drops control characters
