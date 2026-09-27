"""What the park, resume and compact flows work with, injected so tests can fake it."""

import time
from dataclasses import dataclass, field
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
