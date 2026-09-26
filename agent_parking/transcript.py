"""Reading a Claude Code session transcript (`projects/*/<uuid>.jsonl`). Filesystem only."""

from . import records


def find(config_dir, session_id):
    """The transcript of `session_id` under `config_dir`, found by glob rather than by
    rebuilding Claude's project directory name; None when there is none or several."""
    try:
        records.checked_uuid(session_id)
    except ValueError:
        return None
    found = list((config_dir / "projects").glob("*/%s.jsonl" % session_id))
    return found[0] if len(found) == 1 else None
