"""Park records on disk: one JSON file per session UUID. Filesystem only, no Herdr."""

import json
import os
import re

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def checked_uuid(value):
    """`value` when it is a canonical lowercase UUID (what Claude uses), else ValueError.

    Checked before any path is built from it."""
    if not isinstance(value, str) or not UUID.fullmatch(value):
        raise ValueError("not a session UUID: %r" % (value,))
    return value


def _private_dir(directory):
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)  # mkdir's mode is filtered by the umask


def write(directory, record):
    """Write `record` as `<directory>/<session_id>.json`, readable by the owner only."""
    name = checked_uuid(record.get("session_id")) + ".json"
    _private_dir(directory)
    path = directory / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return path
