"""Park records on disk: one JSON file per session UUID. Filesystem only, no Herdr."""

import json
import os


def _private_dir(directory):
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)  # mkdir's mode is filtered by the umask


def write(directory, record):
    """Write `record` as `<directory>/<session_id>.json`, readable by the owner only."""
    _private_dir(directory)
    path = directory / (record["session_id"] + ".json")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return path
