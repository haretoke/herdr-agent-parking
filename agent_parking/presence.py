"""Which dashboard is open on this Herdr server, so `open` moves it instead of piling up
another one (each one polls, and an overlay stays a split of its tab until it closes)."""

import json
import os

from . import storage


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def announce(path, pane_id, pid, placement):
    """The dashboard in `pane_id` (process `pid`, opened as `placement`) is the open one."""
    storage.write_json(path, {"pane_id": pane_id, "pid": pid, "placement": placement})


def current(path, alive=_alive):
    """The open dashboard, or None when none was announced or its process is gone."""
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(found, dict) or not isinstance(found.get("pane_id"), str) \
            or not isinstance(found.get("pid"), int) or not alive(found["pid"]):
        return None
    return found


def release(path, pane_id):
    """Withdraw the announcement when it is still this dashboard's (a newer one may have
    taken over)."""
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(found, dict) and found.get("pane_id") == pane_id:
        path.unlink(missing_ok=True)
