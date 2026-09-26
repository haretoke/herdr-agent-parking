"""Reading a Claude Code session transcript (`projects/*/<uuid>.jsonl`). Filesystem only."""

import json
import os
from collections import namedtuple

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


class Cache:
    """`read(path)` results kept per path until the file's mtime or size changes."""

    def __init__(self, read):
        self.read = read
        self.entries = {}

    def get(self, path):
        if path is None:
            return None
        try:
            stat = os.stat(path)
        except OSError:
            self.entries.pop(path, None)
            return None
        key = (stat.st_mtime_ns, stat.st_size)
        cached = self.entries.get(path)
        if cached is None or cached[0] != key:
            cached = (key, self.read(path))
            self.entries[path] = cached
        return cached[1]


Summary = namedtuple("Summary", "tokens model")


def _usage(row):
    message = row.get("message") if row.get("type") == "assistant" else None
    usage = message.get("usage") if isinstance(message, dict) else None
    return usage if isinstance(usage, dict) else None


def summarize(rows):
    """What the dashboard shows of a transcript's tail.

    `tokens` is Claude's context size: input + cache creation + cache read of the last
    assistant usage after the last compact boundary (the statusline's numerator)."""
    tokens = model = None
    for row in rows:
        if row.get("subtype") == "compact_boundary":
            tokens = model = None
            continue
        usage = _usage(row)
        if usage is not None:
            tokens = sum(usage.get(key) or 0 for key in (
                "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
            model = row["message"].get("model")
    return Summary(tokens=tokens, model=model)
