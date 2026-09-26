"""Putting a parked session's pane back when it was closed (`on_park = close`, or by hand)."""

from collections import namedtuple

# pane_id is the new pane, or None with the reason in message
Placed = namedtuple("Placed", "pane_id message")


def _split(rt, target, direction, cwd):
    result = rt.herdr.call("pane.split", {"target_pane_id": target, "direction": direction, "cwd": cwd,
                                          "focus": False})
    return result["pane"]["pane_id"]


def place(rt, record, panes):
    """A new pane for `record` as close to where it was as the tab allows (spike 0-15)."""
    hint = record.get("layout_hint") or {}
    existing = {p.pane_id: p for p in panes}
    sibling = existing.get(hint.get("sibling_pane_id"))
    if sibling is not None:
        new = _split(rt, sibling.pane_id, hint["direction"], record["cwd"])
        rt.herdr.call("layout.set_split_ratio", {"tab_id": sibling.tab_id, "path": hint["path"],
                                                 "ratio": hint["ratio"]})
        return Placed(new, "")
    return Placed(None, "no place to put the pane back")
