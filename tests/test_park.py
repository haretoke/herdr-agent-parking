import copy
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent_parking import config, herdr_api, park, runtime, state
from tests.fake_herdr import FakeHerdr

UUID = "2716af66-e4d8-4950-8185-97da891f78a9"
NOW = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)


def pane_reply(status="idle", agent="claude", session_id=UUID, label=None, pane_id="w1:p2"):
    pane = {"pane_id": pane_id, "tab_id": "w1:t1", "workspace_id": "w1", "agent": agent,
            "agent_status": status, "cwd": "/repo", "label": label, "terminal_title_stripped": "work"}
    if session_id:
        pane["agent_session"] = {"agent": "claude", "kind": "id", "value": session_id}
    return {"type": "pane_info", "pane": pane}


class ParkTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.environ = {"HOME": self.tmp.name, "HERDR_PLUGIN_ID": state.PLUGIN_ID,
                        "HERDR_PLUGIN_STATE_DIR": str(Path(self.tmp.name) / "state")}
        self.settings = copy.deepcopy(config.DEFAULTS)
        self.slept = []

    def runtime(self, script):
        self.fake = FakeHerdr(script)
        self.addCleanup(self.fake.close)
        return runtime.Runtime(herdr=herdr_api.Herdr(self.fake.path), system=None,
                               paths=state.paths(self.environ, self.settings), settings=self.settings,
                               clock=lambda: NOW, environ=self.environ, sleep=self.slept.append)


class RefuseTest(ParkTestCase):
    def test_only_idle_or_done_panes_can_be_parked(self):
        for status in ("working", "blocked", "unknown"):
            with self.subTest(status=status):
                rt = self.runtime({"pane.get": pane_reply(status=status)})
                outcome = park.park(rt, "w1:p2", note=None)
                self.assertEqual(outcome.kind, "refused")
                self.assertIn(status, outcome.message)
                self.assertEqual(self.fake.methods(), ["pane.get"])


class IntegrationTest(ParkTestCase):
    def test_a_claude_pane_without_a_session_needs_the_herdr_integration(self):
        rt = self.runtime({"pane.get": pane_reply(session_id=None)})
        outcome = park.park(rt, "w1:p2", note=None)
        self.assertEqual(outcome.kind, "refused")
        self.assertIn("herdr integration install claude", outcome.message)
        self.assertEqual(self.fake.methods(), ["pane.get"])


if __name__ == "__main__":
    unittest.main()
