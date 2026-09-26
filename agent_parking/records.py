"""Park records on disk: one JSON file per session UUID. Filesystem only, no Herdr."""

import json
import os
import re
from datetime import timedelta

from . import storage
from .times import iso, parse as parse_time

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SCHEMA_VERSION = 1


class Refused(Exception):
    """A record operation that must not happen; the message says why."""


def checked_uuid(value):
    """`value` when it is a canonical lowercase UUID (what Claude uses), else ValueError.

    Checked before any path is built from it."""
    if not isinstance(value, str) or not UUID.fullmatch(value):
        raise ValueError("not a session UUID: %r" % (value,))
    return value


def write(directory, record):
    """Write `record` as `<directory>/<session_id>.json`, readable by the owner only.

    The file is replaced atomically: a failure midway keeps the previous record."""
    name = checked_uuid(record.get("session_id")) + ".json"
    storage.private_dir(directory)
    path = directory / name
    if path.exists() and not _ours(_read(path)):
        raise Refused("%s has a schema this version does not know" % path.name)
    storage.write_json(path, record)
    return path


def start_parking(directory, record):
    """Write the `parking` record that opens a park, refusing while another park of the
    same session is still in `parking` (two dashboards, or a double key press)."""
    path = directory / (checked_uuid(record.get("session_id")) + ".json")
    current = _read(path) if path.exists() else None
    if current is not None and current.get("status") == "parking":
        raise Refused("session %s is already being parked" % record["session_id"])
    return write(directory, record)


def read(directory, session_id):
    """The record of `session_id` in `directory` when it is one this version can read."""
    path = directory / (checked_uuid(session_id) + ".json")
    current = _read(path) if path.exists() else None
    return current if current is not None and _ours(current) else None


def discard_parking(directory, session_id):
    """Remove the `parking` record of `session_id` (a park that never sent `/exit`)."""
    path = directory / (checked_uuid(session_id) + ".json")
    current = _read(path) if path.exists() else None
    if current is not None and _ours(current) and current.get("status") == "parking":
        path.unlink()


def _read(path):
    """The JSON object in `path`, or None when it is not one."""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _ours(loaded):
    """A readable record of the schema this version writes (broken files count as ours)."""
    return loaded is None or loaded.get("schema_version") == SCHEMA_VERSION


def _record_files(directory):
    """`<uuid>.json` files in `directory`, sorted; temp files and other names are skipped."""
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir()
                  if p.suffix == ".json" and UUID.fullmatch(p.stem) and p.is_file())


def list_records(directory):
    """Every record in `directory`, plus one `{"status": "broken"}` row per file that is
    not a JSON object. Such files are moved to `broken/` once and listed from there. A file
    that vanishes meanwhile (another dashboard settled it) is skipped."""
    listed = []
    for path in _record_files(directory):
        try:
            loaded = _read(path)
            if loaded is None:
                storage.private_dir(directory / "broken")
                os.replace(path, directory / "broken" / path.name)
        except FileNotFoundError:
            continue
        if loaded is not None and _ours(loaded):
            listed.append(loaded)
    for path in _record_files(directory / "broken"):
        listed.append({"session_id": path.stem, "status": "broken"})
    return listed


def mark_resumed(directory, resumed_directory, session_id, now):
    """Move the record of `session_id` to `resumed_directory` as `resumed` at `now`. False
    when it is already gone (another dashboard moved it first)."""
    path = directory / (checked_uuid(session_id) + ".json")
    try:
        current = _read(path)
    except FileNotFoundError:
        return False
    if current is None or not _ours(current):
        raise Refused("%s is not a record this version can move" % path.name)
    write(resumed_directory, dict(current, status="resumed", resumed_at=iso(now)))
    path.unlink(missing_ok=True)
    return True


def purge_resumed(resumed_directory, keep_days, now):
    """Delete resumed records older than `keep_days`; return their session ids.

    Records of an unknown schema and records without a readable time are kept."""
    deleted = []
    for path in _record_files(resumed_directory):
        current = _read(path)
        if current is None or not _ours(current):
            continue
        resumed_at = parse_time(current.get("resumed_at"))
        if resumed_at is not None and now - resumed_at > timedelta(days=keep_days):
            path.unlink()
            deleted.append(path.stem)
    return deleted


def with_pane(record, pane_id):
    """`record` moved to `pane_id`, the previous pane kept in `pane_id_history`."""
    history = list(record.get("pane_id_history") or [])
    previous = record.get("pane_id")
    if previous and previous != pane_id:
        history.append(previous)
    return dict(record, pane_id=pane_id, pane_id_history=history)
