"""What the park, resume and compact flows work with, injected so tests can fake it."""

import time
from dataclasses import dataclass
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
