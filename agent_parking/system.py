"""What the plugin reads about processes outside Herdr: `/proc` on Linux, `ps` elsewhere."""

import ctypes
import ctypes.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
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

    def environ(self, pid):
        """The environment `pid` was started with (`/proc/<pid>/environ` on Linux, the
        kernel's process arguments on macOS), or None when it cannot be read."""
        if self.has_proc():
            data = self._read(pid, "environ")
            return None if data is None else _pairs(data.split(b"\0"))
        if sys.platform == "darwin":
            return _macos_environ(pid)
        return None

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

    def rss_many(self, pids):
        """`{pid: KiB}` for the `pids` that could be read: `VmRSS` where `/proc` exists, else
        one `ps -o pid=,rss= -p a,b,c` for all of them (one per pid cost a process spawn
        each, some 27 every 2 s for nine sessions on the Mac)."""
        pids = [pid for pid in pids if isinstance(pid, int)]
        if not pids:
            return {}
        if self.has_proc():
            return {pid: kib for pid, kib in ((pid, self.rss_kb(pid)) for pid in pids) if kib is not None}
        try:
            done = self.run(["ps", "-o", "pid=,rss=", "-p", ",".join(map(str, pids))],
                            capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return {}
        found = {}
        for line in done.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                found[int(parts[0])] = int(parts[1])
        return found

    def claude_agents(self, command, env):
        """Claude's session list (`claude agents --json`: its interactive and background
        sessions; 0.7 s on the Mac), run with `env` added (a Claude's account), or None when
        it cannot be read (a Claude without the command, a failure)."""
        try:
            done = self.run([command, "agents", "--json"], capture_output=True, text=True, timeout=10,
                            env=dict(os.environ, **env))
            entries = json.loads(done.stdout) if done.returncode == 0 else None
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
        return entries if isinstance(entries, list) else None

    def realpath(self, path):
        return os.path.realpath(path)

    def which(self, command, path):
        """`command` found on the `PATH` string `path`, or None."""
        return shutil.which(command, path=path)


def _pairs(items):
    found = {}
    for item in items:
        name, sep, value = item.partition(b"=")
        if sep and name:
            found[name.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    return found


def _macos_environ(pid):
    """The environment in `sysctl(KERN_PROCARGS2)`: argc, the executable path, padding, argv
    and then the environment, all NUL-separated (only for processes of this user)."""
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    ctl_kern, kern_argmax, kern_procargs2 = 1, 8, 49
    argmax = ctypes.c_int(0)
    size = ctypes.c_size_t(ctypes.sizeof(argmax))
    if libc.sysctl((ctypes.c_int * 2)(ctl_kern, kern_argmax), 2, ctypes.byref(argmax), ctypes.byref(size),
                   None, 0) != 0:
        return None
    buffer = ctypes.create_string_buffer(argmax.value)
    size = ctypes.c_size_t(argmax.value)
    if libc.sysctl((ctypes.c_int * 3)(ctl_kern, kern_procargs2, pid), 3, buffer, ctypes.byref(size),
                   None, 0) != 0:
        return None
    data = buffer.raw[:size.value]
    if len(data) < 4:
        return None
    argc = struct.unpack("i", data[:4])[0]
    rest = data[4:]
    start = rest.find(b"\0")
    if start < 0:
        return None
    while start < len(rest) and rest[start] == 0:
        start += 1
    parts = rest[start:].split(b"\0")
    environment = []
    for item in parts[argc:]:
        if not item:
            break
        environment.append(item)
    return _pairs(environment)
