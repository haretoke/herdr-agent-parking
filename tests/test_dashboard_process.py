"""The dashboard as a process in a pseudo-terminal, against a fake Herdr socket."""

import fcntl
import os
import select
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from pathlib import Path

from agent_parking import state
from tests.fake_herdr import FakeHerdr

REPOSITORY = Path(__file__).resolve().parents[1]
UUID = "2716af66-e4d8-4950-8185-97da891f78a9"


def claude_pane(pane_id="w1:p2", title="api gateway"):
    return {"pane_id": pane_id, "tab_id": "w1:t1", "workspace_id": "w1", "agent": "claude",
            "agent_status": "idle", "cwd": "/repo", "label": None, "terminal_title_stripped": title,
            "agent_session": {"agent": "claude", "kind": "id", "value": UUID}}


def script(*panes):
    return {"pane.list": {"type": "pane_list", "panes": list(panes)},
            "agent.list": {"type": "agent_list", "agents": []},
            "workspace.list": {"type": "workspace_list", "workspaces": []},
            "tab.list": {"type": "tab_list", "tabs": []},
            "pane.process_info": {"type": "process_info", "process_info": {}}}


class DashboardProcessTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.state_dir = self.home / "state"
        self.output = b""

    def start(self, herdr_script, rows=24, cols=80):
        """The dashboard on the slave side of a pty. subprocess instead of pty.fork: forking
        a process that runs the fake server's threads is unsafe."""
        self.herdr = FakeHerdr(herdr_script)
        self.addCleanup(self.herdr.close)
        master, slave = os.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        env = {"PATH": "/usr/bin:/bin", "HOME": str(self.home), "HERDR_SOCKET_PATH": self.herdr.path,
               "HERDR_PANE_ID": "w1:p9", "HERDR_PLUGIN_ID": state.PLUGIN_ID,
               "HERDR_PLUGIN_STATE_DIR": str(self.state_dir)}
        process = subprocess.Popen([sys.executable, "-m", "agent_parking", "dashboard"], stdin=slave,
                                   stdout=slave, stderr=slave, cwd=REPOSITORY, env=env, start_new_session=True)
        os.close(slave)
        self.addCleanup(self.kill, process)
        self.addCleanup(os.close, master)
        return process, master

    def kill(self, process):
        if process.poll() is None:
            process.kill()
        process.wait()

    def drain(self, master, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.05)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    return
                if not chunk:
                    return
                self.output += chunk

    def wait_for(self, master, text, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if text in self.output:
                return
            self.drain(master, 0.05)
        self.fail("%r never appeared in %r" % (text, self.output[-300:]))

    def wait_exit(self, process, master, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.drain(master, 0.05)
            if process.poll() is not None:
                return process.returncode
        self.fail("the dashboard did not exit")


class StartTest(DashboardProcessTestCase):
    def test_the_list_is_drawn_at_start_and_q_closes_it(self):
        process, master = self.start(script(claude_pane()))
        self.wait_for(master, b"api gateway")
        self.assertIn(b"Agent parking", self.output)
        self.assertIn(b"\x1b[?1049h", self.output)  # alternate screen entered

        os.write(master, b"q")

        self.assertEqual(self.wait_exit(process, master), 0)
        self.assertIn(b"\x1b[?1049l", self.output)  # and left
        self.assertIn(b"\x1b[?25h", self.output)  # cursor shown again


if __name__ == "__main__":
    unittest.main()
