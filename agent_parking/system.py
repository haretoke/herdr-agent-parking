"""What the plugin reads about processes outside Herdr: `/proc` on Linux, `ps` elsewhere."""

import os
import re
import subprocess
from pathlib import Path

VMRSS = re.compile(rb"^VmRSS:\s*(\d+)\s*kB", re.M)


class System:
    def __init__(self, proc_root=Path("/proc"), run=subprocess.run):
        self.proc_root = Path(proc_root)
        self.run = run

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

    def rss_kb(self, pid):
        """Resident memory of `pid` in KiB: `VmRSS` where `/proc` exists, else `ps -o rss=`
        (KiB on macOS and Linux; spike 0-9). None when it cannot be read."""
        if self.has_proc():
            match = VMRSS.search(self._read(pid, "status") or b"")
            return int(match.group(1)) if match else None
        try:
            done = self.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return None
        text = done.stdout.strip() if done.returncode == 0 else ""
        return int(text) if text.isdigit() else None
