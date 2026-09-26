import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent_parking import config, herdr_api, park, runtime, state
from tests.fake_herdr import FakeHerdr
from tests.fakes import FakeSystem

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


RULE = "─" * 40


def screen_reply(input_line):
    text = "\r\n".join(["⏺ OK", RULE, input_line, RULE, "  ctx 18%"])
    return {"type": "agent_read", "read": {"pane_id": "w1:p2", "workspace_id": "w1", "tab_id": "w1:t1",
                                           "source": "visible", "format": "ansi", "text": text,
                                           "revision": 1, "truncated": False}}


class DraftTest(ParkTestCase):
    def test_a_half_typed_line_is_refused_and_no_exit_is_sent(self):
        rt = self.runtime({"pane.get": pane_reply(), "agent.read": screen_reply("❯ half typed line")})
        outcome = park.park(rt, "w1:p2", note=None)
        self.assertEqual(outcome.kind, "refused")
        self.assertIn("draft", outcome.message)
        self.assertNotIn("agent.prompt", self.fake.methods())
        read = [r for r in self.fake.requests if r["method"] == "agent.read"][0]
        self.assertEqual(read["params"], {"target": "w1:p2", "source": "visible", "format": "ansi",
                                          "strip_ansi": False})


SHELL = pane_reply(status="unknown", agent=None, session_id=None)
PROCESS = {"type": "process_info", "process_info": {
    "shell_pid": 100, "foreground_process_group_id": 200,
    "foreground_processes": [{"pid": 200, "name": "2.1.283", "cwd": "/repo",
                              "argv": ["/home/u/.local/bin/claude", "--model", "haiku"]},
                             {"pid": 201, "name": "node"}]}}
SHELL_PROCESS = {"type": "process_info", "process_info": {
    "shell_pid": 100, "foreground_process_group_id": 100,
    "foreground_processes": [{"pid": 100, "name": "zsh"}]}}


class FlowTestCase(ParkTestCase):
    def flow(self, **overrides):
        script = {"pane.get": [pane_reply(), SHELL], "agent.read": screen_reply("❯"),
                  "pane.process_info": [PROCESS, SHELL_PROCESS], "agent.prompt": {"type": "ok"},
                  "pane.rename": {"type": "pane_info"}}
        script.update(overrides)
        rt = self.runtime(script)
        rt.system = FakeSystem(proc=False)
        return rt

    def saved(self):
        path = Path(self.environ["HERDR_PLUGIN_STATE_DIR"]) / "records" / (UUID + ".json")
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


class OrderTest(FlowTestCase):
    def test_the_record_is_on_disk_before_exit_is_sent(self):
        seen = {}

        def exit_prompt(fake, connection, reader, request):
            seen["record"] = self.saved()
            fake.reply(connection, request)

        rt = self.flow(**{"agent.prompt": exit_prompt})
        outcome = park.park(rt, "w1:p2", note=None)
        self.assertEqual(outcome.kind, "parked")
        self.assertEqual(seen["record"]["status"], "parking")
        self.assertEqual(seen["record"]["session_id"], UUID)
        self.assertLess(self.fake.methods().index("pane.process_info"), self.fake.methods().index("agent.prompt"))


class ConfirmationTest(unittest.TestCase):
    def test_the_confirmation_names_the_session_and_always_warns_about_lost_work(self):
        from agent_parking.inventory import Row
        for row in (Row(pane_id="w8:p36", name="proto_tunnel", status="idle"), Row(pane_id="w1:p2")):
            with self.subTest(row=row):
                text = "\n".join(park.confirmation(row))
                self.assertIn(row.pane_id, text)
                self.assertIn("background tasks", text)
                self.assertIn("subagents", text)


if __name__ == "__main__":
    unittest.main()
