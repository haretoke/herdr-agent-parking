"""The dashboard's table: which columns fit the pane and how each row is drawn.

Narrow panes drop the lowest-priority columns first and give the space to the name
(decided with Fable, 2026-09-27; see DESIGN.md, "UI and keys").
"""

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
FIXED = {"place": 14, "place_id": 12, "status": 8, "idle": 6, "ctx": 13, "ctx_short": 7, "rss": 5, "ver": 11}


def widths(cols, width):
    """Each column's width at `width`: the fixed ones, and the rest for the name (at least
    `MIN_NAME`, even when that makes the line too wide; it is cut when drawn)."""
    fixed = {c: FIXED[c] for c in cols if c != "name"}
    rest = width - MARK_WIDTH - sum(fixed.values()) - (len(cols) - 1)
    return dict(fixed, name=max(MIN_NAME, rest))


def _pad(text, columns):
    text = display.cell(text, columns)
    return text + " " * (columns - display.width(text))


def line(cells, width, selected):
    """One row of the table at `width`, cut to the width when the name's minimum overflows it."""
    cols = columns(width)
    sizes = widths(cols, width)
    shown = dict(cells)
    if "ver" not in cols:
        shown["status"] += cells["old"]
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


def _ids(row):
    """`w8/t3/p36` from the workspace, tab and pane ids (`w8:t3`, `w8:p36`)."""
    if not row.pane_id:
        return "(no pane)"
    parts = [row.workspace_id] + [(i or "").split(":")[-1] for i in (row.tab_id, row.pane_id)]
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
    ids = _ids(row)
    if row.record is not None:
        place = place_id = ids + " " + PARKED_MARK
    else:
        label = row.label or row.tab_label or row.workspace_label
        place, place_id = (ids + " " + label if label else ids), ids
    return {"place": place, "place_id": place_id, "name": row.name or "", "status": row.status or "",
            "idle": row.idle, "ctx": row.ctx, "ctx_short": _short_ctx(row.ctx),
            "rss": "—" if row.record is not None else memory(row.rss_kb),
            "ver": (row.version or "") + (" old" if row.old else ""), "old": "!" if row.old else "",
            "account": inventory.account_name(row.env)}
