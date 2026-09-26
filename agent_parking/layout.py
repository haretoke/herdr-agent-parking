"""Where a pane sits in its tab's split tree (`layout.export`), to put it back later."""


def hint(root, pane_id):
    """The split that holds `pane_id`: its sibling pane (None when the sibling is a
    subtree), whether the pane is the `first` or `second` child, the split's direction
    and ratio, and the path to it (booleans, `True` for second; `layout.set_split_ratio`
    takes that form). None for a lone pane or one not in the tree."""
    return _find(root, pane_id, [])


def _find(node, pane_id, path):
    if not isinstance(node, dict) or node.get("type") != "split":
        return None
    for position, other, step in (("first", "second", False), ("second", "first", True)):
        child = node.get(position) or {}
        if child.get("type") == "pane" and child.get("pane_id") == pane_id:
            sibling = node.get(other) or {}
            return {"sibling_pane_id": sibling.get("pane_id") if sibling.get("type") == "pane" else None,
                    "position": position, "direction": node.get("direction"),
                    "ratio": node.get("ratio"), "path": list(path)}
        found = _find(child, pane_id, path + [step])
        if found is not None:
            return found
    return None
