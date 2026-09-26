"""What the plugin reads about processes outside Herdr: `/proc` on Linux, `ps` elsewhere."""

import os
from pathlib import Path


class System:
    def __init__(self, proc_root=Path("/proc")):
        self.proc_root = Path(proc_root)

    def _read(self, pid, name):
        try:
            return (self.proc_root / str(pid) / name).read_bytes()
        except OSError:
            return None

    def cmdline(self, pid):
        """The argv of `pid` from `/proc/<pid>/cmdline`, or None."""
        data = self._read(pid, "cmdline")
        if not data:
            return None
        return [part.decode("utf-8", "replace") for part in data.rstrip(b"\0").split(b"\0")]

    def has_proc(self):
        return self.proc_root.is_dir()

    def exe(self, pid):
        """Where `/proc/<pid>/exe` points (the running executable), or None."""
        try:
            return os.readlink(self.proc_root / str(pid) / "exe")
        except OSError:
            return None
