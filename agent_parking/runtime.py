"""What the park, resume and compact flows work with, injected so tests can fake it."""

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class Runtime:
    herdr: Any            # herdr_api.Herdr
    system: Any           # system.System
    paths: Any            # state.Paths
    settings: dict
    clock: Callable       # () -> aware datetime
    environ: dict
    sleep: Callable = time.sleep
    summary_for: Callable = lambda session_id: None   # session id -> transcript.Summary
    rows_for: Callable = lambda session_id: []        # session id -> transcript tail rows
    statusline_windows: dict = field(default_factory=dict)  # session id -> window size
    has_transcript: Callable = lambda session_id: True       # a Claude never prompted has none
    claude_config_dirs: list = field(default_factory=list)   # where transcripts are looked up


def remember_config_dir(rt, env):
    """Look up transcripts in `env`'s `CLAUDE_CONFIG_DIR` too (a Claude, live or parked,
    that keeps its account apart that way)."""
    given = (env or {}).get("CLAUDE_CONFIG_DIR", "")
    if os.path.isabs(given) and Path(given) not in rt.claude_config_dirs:
        rt.claude_config_dirs.append(Path(given))
