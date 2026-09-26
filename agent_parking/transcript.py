"""Reading a Claude Code session transcript (`projects/*/<uuid>.jsonl`). Filesystem only."""

import json
import os

from . import records

TAIL_BYTES = 1024 * 1024


def find(config_dir, session_id):
    """The transcript of `session_id` under `config_dir`, found by glob rather than by
    rebuilding Claude's project directory name; None when there is none or several."""
    try:
        records.checked_uuid(session_id)
    except ValueError:
        return None
    found = list((config_dir / "projects").glob("*/%s.jsonl" % session_id))
    return found[0] if len(found) == 1 else None


def read_tail(path, cap=TAIL_BYTES):
    """The JSON object lines of the last `cap` bytes of `path`. A line cut by the cap is
    dropped; the rest of the file is never loaded."""
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        start = max(0, size - cap)
        cut_mid_line = False
        if start > 0:
            f.seek(start - 1)
            cut_mid_line = f.read(1) != b"\n"
        f.seek(start)
        data = f.read(size - start)
    lines = data.split(b"\n")
    if cut_mid_line:
        lines = lines[1:]
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows
