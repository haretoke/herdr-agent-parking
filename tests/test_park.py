import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent_parking import config, herdr_api, park, runtime, state, transcript
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


class RecordFieldsTest(FlowTestCase):
    def test_what_is_read_before_exit_is_in_the_parking_record(self):
        seen = {}

        def exit_prompt(fake, connection, reader, request):
            seen["record"] = self.saved()
            fake.reply(connection, request)

        rt = self.flow(**{"agent.prompt": exit_prompt,
                          "pane.get": [pane_reply(label="api"), SHELL]})
        rt.summary_for = lambda session_id: transcript.EMPTY._replace(tokens=36890, model="claude-haiku-4-5")
        self.settings["context_window_by_model"] = {"claude-haiku": 200_000}
        outcome = park.park(rt, "w1:p2", note=None)
        before = seen["record"]
        self.assertEqual(before["argv"], ["/home/u/.local/bin/claude", "--model", "haiku"])
        self.assertEqual(before["claude_version"], "2.1.283")
        self.assertEqual(before["label_before"], "api")
        self.assertEqual(before["context_at_park"], {"tokens": 36890, "percent": 18, "compacted": False})
        self.assertEqual((before["title"], before["cwd"], before["tab_id"], before["workspace_id"]),
                         ("work", "/repo", "w1:t1", "w1"))
        self.assertEqual(before["parked_at"], "2026-09-27T12:00:00Z")
        self.assertIn("layout_hint", before)
        self.assertNotIn("parked_mode", before)
        self.assertEqual(outcome.record["parked_mode"], "keep")
        self.assertEqual(self.saved()["parked_mode"], "keep")


class ExitTest(FlowTestCase):
    def test_exit_is_a_plain_agent_prompt_without_a_wait(self):
        park.park(self.flow(), "w1:p2", note=None)
        [prompt] = [r for r in self.fake.requests if r["method"] == "agent.prompt"]
        self.assertEqual(prompt["params"], {"target": "w1:p2", "text": "/exit"})


class LabelTest(FlowTestCase):
    def test_after_the_shell_is_back_the_pane_is_labelled_and_the_old_label_kept(self):
        rt = self.flow(**{"pane.get": [pane_reply(label="api"), pane_reply(label="api"), SHELL]})
        outcome = park.park(rt, "w1:p2", note=None)
        self.assertEqual(outcome.kind, "parked")
        self.assertEqual(len(self.slept), 1)
        [rename] = [r for r in self.fake.requests if r["method"] == "pane.rename"]
        self.assertEqual(rename["params"], {"pane_id": "w1:p2", "label": "💤 work"})
        self.assertLess(self.fake.methods().index("agent.prompt"), self.fake.methods().index("pane.rename"))
        self.assertEqual(self.saved()["label_before"], "api")


class LayoutHintTest(FlowTestCase):
    def test_the_layout_hint_comes_from_the_tab_tree_before_exit(self):
        tree = {"type": "split", "direction": "right", "ratio": 0.3,
                "first": {"type": "pane", "pane_id": "w1:p1"}, "second": {"type": "pane", "pane_id": "w1:p2"}}
        rt = self.flow(**{"layout.export": {"type": "layout_export", "workspace_id": "w1", "tab_id": "w1:t1",
                                            "root": tree}})
        park.park(rt, "w1:p2", note=None)
        [export] = [r for r in self.fake.requests if r["method"] == "layout.export"]
        self.assertEqual(export["params"], {"pane_id": "w1:p2"})
        self.assertLess(self.fake.methods().index("layout.export"), self.fake.methods().index("agent.prompt"))
        self.assertEqual(self.saved()["layout_hint"], {"sibling_pane_id": "w1:p1", "position": "second",
                                                       "direction": "right", "ratio": 0.3, "path": []})

    def test_a_failing_export_leaves_no_hint_and_the_park_goes_on(self):
        outcome = park.park(self.flow(), "w1:p2", note=None)
        self.assertEqual(outcome.kind, "parked")
        self.assertIsNone(self.saved()["layout_hint"])


TWO_PANES = {"type": "layout_export", "tab_id": "w1:t1", "root": {
    "type": "split", "direction": "right", "ratio": 0.5,
    "first": {"type": "pane", "pane_id": "w1:p1"}, "second": {"type": "pane", "pane_id": "w1:p2"}}}
ONE_PANE = {"type": "layout_export", "tab_id": "w1:t1", "root": {"type": "pane", "pane_id": "w1:p2"}}


class OnParkTest(FlowTestCase):
    def test_by_default_the_pane_stays(self):
        outcome = park.park(self.flow(**{"layout.export": TWO_PANES}), "w1:p2", note=None)
        self.assertNotIn("pane.close", self.fake.methods())
        self.assertEqual(outcome.record["parked_mode"], "keep")

    def test_close_closes_the_pane_once_the_shell_alone_is_back(self):
        self.settings["on_park"] = "close"
        outcome = park.park(self.flow(**{"layout.export": TWO_PANES, "pane.close": {"type": "ok"}}),
                            "w1:p2", note=None)
        [close] = [r for r in self.fake.requests if r["method"] == "pane.close"]
        self.assertEqual(close["params"], {"pane_id": "w1:p2"})
        self.assertNotIn("pane.rename", self.fake.methods())
        self.assertEqual((outcome.kind, outcome.record["parked_mode"]), ("parked", "close"))
        self.assertEqual(self.saved()["parked_mode"], "close")

    def test_close_keeps_the_last_pane_of_a_tab_and_a_busy_pane(self):
        self.settings["on_park"] = "close"
        busy = {"type": "process_info", "process_info": {"shell_pid": 100, "foreground_process_group_id": 300,
                                                         "foreground_processes": [{"pid": 300, "name": "vim"}]}}
        for overrides, reason in [({"layout.export": ONE_PANE}, "last pane"),
                                  ({"layout.export": TWO_PANES, "pane.process_info": [PROCESS, busy]}, "shell")]:
            with self.subTest(reason=reason):
                outcome = park.park(self.flow(**overrides), "w1:p2", note=None)
                self.assertNotIn("pane.close", self.fake.methods())
                self.assertIn("pane.rename", self.fake.methods())
                self.assertEqual(outcome.record["parked_mode"], "keep")
                self.assertIn(reason, outcome.message)


class TimeoutTest(FlowTestCase):
    def test_claude_still_there_after_the_timeout_is_park_failed_and_the_pane_untouched(self):
        self.settings["exit_timeout_seconds"] = 1
        outcome = park.park(self.flow(**{"pane.get": pane_reply()}), "w1:p2", note=None)
        self.assertEqual(outcome.kind, "park_failed")
        self.assertIn("did not exit", outcome.message)
        self.assertEqual(self.saved()["status"], "park_failed")
        self.assertNotIn("pane.rename", self.fake.methods())
        self.assertNotIn("pane.close", self.fake.methods())
        self.assertEqual(sum(self.slept), 1.0)


class BlockedTest(FlowTestCase):
    def test_a_blocked_claude_refuses_the_exit_and_the_parking_record_goes(self):
        from tests.fake_herdr import Error
        rt = self.flow(**{"agent.prompt": Error("agent_blocked", "agent is waiting at a dialog")})
        outcome = park.park(rt, "w1:p2", note=None)
        self.assertEqual(outcome.kind, "refused")
        self.assertIn("dialog", outcome.message)
        self.assertIsNone(self.saved())
        self.assertNotIn("pane.rename", self.fake.methods())


class NoteTest(FlowTestCase):
    def test_the_note_is_stored_and_an_empty_one_is_null(self):
        for note, stored in [("LUT の一覧を貼る前で止めた\n次は色域", "LUT の一覧を貼る前で止めた\n次は色域"),
                             ("", None), ("  \n ", None), (None, None)]:
            with self.subTest(note=note):
                park.park(self.flow(), "w1:p2", note=note)
                self.assertEqual(self.saved()["note"], stored)


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
