"""Reading a Claude Code session transcript (`projects/*/<uuid>.jsonl`). Filesystem only."""

import json
import os
import re
from collections import namedtuple
from . import records
from .times import parse as parse_time

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


Summary = namedtuple("Summary", "tokens model compacted compacted_at")


EMPTY = Summary(tokens=None, model=None, compacted=False, compacted_at=None)


def load(path, cap=TAIL_BYTES):
    """The summary of the transcript at `path`; EMPTY when it cannot be read."""
    try:
        return summarize(read_tail(path, cap))
    except OSError:
        return EMPTY


def _usage(row):
    message = row.get("message") if row.get("type") == "assistant" else None
    usage = message.get("usage") if isinstance(message, dict) else None
    return usage if isinstance(usage, dict) else None


def summarize(rows):
    """What the dashboard shows of a transcript's tail.

    `tokens` is Claude's context size: input + cache creation + cache read of the last
    assistant usage after the last compact boundary (the statusline's numerator).
    The session is `compacted` while no assistant usage follows the last boundary; the
    summary after a boundary is a `user` line (`isCompactSummary`), so it does not count
    (spike 0-20). `compacted_at` is that boundary's time."""
    tokens = model = compacted_at = None
    compacted = False
    for row in rows:
        if row.get("subtype") == "compact_boundary":
            tokens = model = None
            compacted, compacted_at = True, parse_time(row.get("timestamp"))
            continue
        usage = _usage(row)
        if usage is not None:
            tokens = sum(usage.get(key) or 0 for key in (
                "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
            model = row["message"].get("model")
            compacted, compacted_at = False, None
    return Summary(tokens=tokens, model=model, compacted=compacted, compacted_at=compacted_at)


def window_size(model, session_id, by_model, from_statusline):
    """The context window in tokens: the longest `context_window_by_model` prefix of
    `model`, else the statusline's value for the session, else None (unknown)."""
    if model:
        prefixes = [prefix for prefix in by_model if model.startswith(prefix)]
        if prefixes:
            return by_model[max(prefixes, key=len)]
    return from_statusline.get(session_id)


def statusline_windows(path):
    """`{session_id: context_window_size}` written by the optional statusline hook-up;
    anything unreadable or malformed is left out."""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {key: value for key, value in loaded.items()
            if records.UUID.fullmatch(key) and isinstance(value, int)
            and not isinstance(value, bool) and value > 0}


def percent(tokens, window):
    """The share of the window in use, truncated like Claude's statusline
    (36890 / 200000 → 18); None when either side is unknown."""
    if tokens is None or not window:
        return None
    return tokens * 100 // window


Reply = namedtuple("Reply", "found text focus")
FOCUS = re.compile(r"<compact-focus>(.*?)</compact-focus>", re.S)


def _text(row):
    message = row.get("message") if isinstance(row.get("message"), dict) else {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    return "\n".join(item.get("text", "") for item in content or []
                     if isinstance(item, dict) and item.get("type") == "text")


def _is_prompt(row, prompt):
    """The user line of `prompt`: its own text, or for a slash command the
    `<command-name>` line Claude writes for it."""
    if row.get("type") != "user" or row.get("isMeta"):
        return False
    text = _text(row)
    if text.strip() == prompt.strip():
        return True
    command = prompt.split()[0] if prompt.startswith("/") else None
    return command is not None and ("<command-name>%s</command-name>" % command) in text


def preparation_reply(rows, prompt):
    """The assistant's reply to the last `prompt` in `rows`, and the one-line focus of its
    last `<compact-focus>` tag ("" without one)."""
    starts = [i for i, row in enumerate(rows) if _is_prompt(row, prompt)]
    if not starts:
        return Reply(found=False, text="", focus="")
    texts = [_text(row) for row in rows[starts[-1] + 1:] if row.get("type") == "assistant"]
    text = "\n".join(t for t in texts if t)
    tags = FOCUS.findall(text)
    focus = " ".join(tags[-1].split()) if tags else ""
    return Reply(found=True, text=text, focus=focus)


def compacted_since(rows, moment):
    """A compact boundary written at or after `moment` (the flow's proof that the
    `/compact` it sent finished; spike 0-21)."""
    for row in rows:
        if row.get("subtype") == "compact_boundary":
            at = parse_time(row.get("timestamp"))
            if at is not None and at >= moment:
                return True
    return False
