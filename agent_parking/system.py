"""What the plugin reads about processes outside Herdr: `/proc` on Linux, `ps` elsewhere."""

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
