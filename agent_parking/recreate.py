"""Putting a parked session's pane back when it was closed (`on_park = close`, or by hand)."""

from collections import namedtuple

# pane_id is the new pane, or None with the reason in message
Placed = namedtuple("Placed", "pane_id message")
NEEDS_WORKSPACE = "its workspace is gone too; create a new workspace for it?"


def _split(rt, target, direction, cwd):
    result = rt.herdr.call("pane.split", {"target_pane_id": target, "direction": direction, "cwd": cwd,
                                          "focus": False})
    return result["pane"]["pane_id"]


def place(rt, record, panes, new_workspace=False):
    """A new pane for `record` as close to where it was as the tab allows (spike 0-15).
    A new workspace is only created with `new_workspace` (asked first, NEEDS_WORKSPACE)."""
    if not record.get("cwd"):
        return Placed(None, "the record has no cwd to open the pane in; resume it by hand with "
                            "`claude --resume %s` where it belongs" % record["session_id"])
    hint = record.get("layout_hint") or {}
    existing = {p.pane_id: p for p in panes}
    sibling = existing.get(hint.get("sibling_pane_id"))
    if sibling is not None:
        new = _split(rt, sibling.pane_id, hint["direction"], record["cwd"])
        if hint["position"] == "first":
            # Splits only go right or down; the swap puts the new pane on the left or top.
            rt.herdr.call("pane.swap", {"source_pane_id": new, "target_pane_id": sibling.pane_id})
        rt.herdr.call("layout.set_split_ratio", {"tab_id": sibling.tab_id, "path": hint["path"],
                                                 "ratio": hint["ratio"]})
        return Placed(new, "")
    # The sibling was a subtree or is gone: right/down splits cannot rebuild the old
    # position, so the pane goes beside any pane of its tab.
    in_tab = [p for p in panes if p.tab_id == record.get("tab_id")]
    if in_tab:
        return Placed(_split(rt, in_tab[0].pane_id, "right", record["cwd"]), "")
    if any(p.workspace_id == record.get("workspace_id") for p in panes):
        result = rt.herdr.call("tab.create", {"workspace_id": record["workspace_id"], "cwd": record["cwd"],
                                              "label": record.get("tab_label"), "focus": False})
        return Placed(result["root_pane"]["pane_id"], "")
    if not new_workspace:
        return Placed(None, NEEDS_WORKSPACE)
    result = rt.herdr.call("workspace.create", {"cwd": record["cwd"], "label": record.get("workspace_label"),
                                                "focus": False})
    return Placed(result["root_pane"]["pane_id"], "")
