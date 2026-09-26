"""The plugin's settings: `config.json` in Herdr's plugin config directory."""

import copy
import json
from collections import namedtuple

DEFAULTS = {
    "poll_seconds": 2,
    "exit_timeout_seconds": 20,
    "start_timeout_ms": 30000,
    "on_park": "keep",
    "parked_label_format": "💤 {title}",
    "send_note_as_prompt": False,
    "bulk_idle_minutes": 60,
    "claude_command": "claude",
    "resumed_keep_days": 30,
    "records_dir": None,
    "claude_config_dir": None,
    "context_window_by_model": {},
    "prepare_command": "/prepare-compact",
    "prepare_prompt": None,
    "prepare_timeout_seconds": 600,
    "compact_timeout_seconds": 300,
}


BUILT_IN_PREPARE_PROMPT = (
    "I am about to run /compact. Before that: save anything that lives only in this "
    "conversation (decisions, identifiers, progress, next steps) to the project's notes "
    "or your memory; report uncommitted and unpushed work without committing or pushing "
    "unless I asked for it; stop background processes and delete temporary files you "
    "started; list open items. Do not start new work. End with one line of at most 300 "
    "characters, in my language, naming what the summary must keep, in exactly this "
    "form: <compact-focus>...</compact-focus>"
)

# What `c` sends first, and what it sends when that turns out to be an unknown
# command (the skill is missing). An explicit prepare_prompt has no fallback.
Preparation = namedtuple("Preparation", "first fallback")


def preparation(settings):
    if settings["prepare_prompt"]:
        return Preparation(first=settings["prepare_prompt"], fallback=None)
    return Preparation(first=settings["prepare_command"], fallback=BUILT_IN_PREPARE_PROMPT)


def _positive_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _text(value):
    return isinstance(value, str) and value != ""


def _optional_text(value):
    return value is None or _text(value)


VALID = {
    "poll_seconds": _positive_number,
    "exit_timeout_seconds": _positive_number,
    "start_timeout_ms": _positive_number,
    "on_park": lambda value: value in ("keep", "close"),
    "parked_label_format": _text,
    "send_note_as_prompt": lambda value: isinstance(value, bool),
    "bulk_idle_minutes": _positive_number,
    "claude_command": _text,
    "resumed_keep_days": _positive_number,
    "records_dir": _optional_text,
    "claude_config_dir": _optional_text,
    "context_window_by_model": lambda value: isinstance(value, dict),
    "prepare_command": _text,
    "prepare_prompt": _optional_text,
    "prepare_timeout_seconds": _positive_number,
    "compact_timeout_seconds": _positive_number,
}


def load(path, log):
    """The settings from `path` over the defaults; `log` gets one line per problem.

    A missing file is the normal case and is not logged.
    """
    settings = copy.deepcopy(DEFAULTS)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return settings
    if not text.strip():
        log("%s is empty; using the defaults" % path)
        return settings
    try:
        given = json.loads(text)
    except ValueError as error:
        log("%s is not valid JSON (%s); using the defaults" % (path, error))
        return settings
    if not isinstance(given, dict):
        log("%s is not a JSON object; using the defaults" % path)
        return settings
    for key, value in given.items():
        if key not in VALID:
            log("%s: unknown key %r is ignored" % (path, key))
        elif not VALID[key](value):
            log("%s: %s = %r is not valid; using %r" % (path, key, value, DEFAULTS[key]))
        elif key == "context_window_by_model":
            settings[key] = _context_windows(value, lambda line: log("%s: %s" % (path, line)))
        else:
            settings[key] = value
    return settings


def _context_windows(given, log):
    """The entries of `context_window_by_model` that map a model id prefix to a
    positive integer token count."""
    kept = {}
    for prefix, tokens in given.items():
        if prefix and isinstance(tokens, int) and not isinstance(tokens, bool) and tokens > 0:
            kept[prefix] = tokens
        else:
            log("context_window_by_model[%r] = %r is ignored" % (prefix, tokens))
    return kept
