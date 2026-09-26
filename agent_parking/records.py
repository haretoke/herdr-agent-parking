"""Park records on disk: one JSON file per session UUID. Filesystem only, no Herdr."""

import json
import os
import re
from datetime import datetime, timedelta, timezone

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


def _private_dir(directory):
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)  # mkdir's mode is filtered by the umask


def write(directory, record):
    """Write `record` as `<directory>/<session_id>.json`, readable by the owner only.

    The file is replaced atomically: a failure midway keeps the previous record."""
    name = checked_uuid(record.get("session_id")) + ".json"
    _private_dir(directory)
    path = directory / name
    if path.exists() and not _ours(_read(path)):
        raise Refused("%s has a schema this version does not know" % path.name)
    tmp = directory / (".%s.%d.tmp" % (name, os.getpid()))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def start_parking(directory, record):
    """Write the `parking` record that opens a park, refusing while another park of the
    same session is still in `parking` (two dashboards, or a double key press)."""
    path = directory / (checked_uuid(record.get("session_id")) + ".json")
    current = _read(path) if path.exists() else None
    if current is not None and current.get("status") == "parking":
        raise Refused("session %s is already being parked" % record["session_id"])
    return write(directory, record)


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
    not a JSON object. Such files are moved to `broken/` once and listed from there."""
    listed = []
    for path in _record_files(directory):
        loaded = _read(path)
        if loaded is None:
            _private_dir(directory / "broken")
            os.replace(path, directory / "broken" / path.name)
        elif _ours(loaded):
            listed.append(loaded)
    for path in _record_files(directory / "broken"):
        listed.append({"session_id": path.stem, "status": "broken"})
    return listed


def iso(moment):
    """`moment` (an aware datetime) as the records' UTC text, `2026-09-27T12:00:00Z`."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text):
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def mark_resumed(directory, resumed_directory, session_id, now):
    """Move the record of `session_id` to `resumed_directory` as `resumed` at `now`."""
    path = directory / (checked_uuid(session_id) + ".json")
    current = _read(path)
    if current is None or not _ours(current):
        raise Refused("%s is not a record this version can move" % path.name)
    write(resumed_directory, dict(current, status="resumed", resumed_at=iso(now)))
    path.unlink()


def purge_resumed(resumed_directory, keep_days, now):
    """Delete resumed records older than `keep_days`; return their session ids.

    Records of an unknown schema and records without a readable time are kept."""
    deleted = []
    for path in _record_files(resumed_directory):
        current = _read(path)
        if current is None or not _ours(current):
            continue
        resumed_at = _parse_iso(current.get("resumed_at"))
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
