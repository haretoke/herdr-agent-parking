"""The dashboard's private log, for errors nobody would otherwise see (a crashing plugin
pane closes and takes its output with it)."""

import os
import time

from . import storage


def append(path, text):
    """Append a timestamped entry to the 0600 log at `path`; never raises."""
    try:
        storage.private_dir(path.parent)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write("%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), text.rstrip()))
    except OSError:
        pass  # nowhere left to report it
