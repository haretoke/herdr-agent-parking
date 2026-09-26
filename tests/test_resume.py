import json
import unittest
from pathlib import Path

from agent_parking import records, resume
from tests.flows import NOW, SHELL, SHELL_PROCESS, UUID, FlowTestCase, pane_reply

PARKED = {"schema_version": 1, "session_id": UUID, "status": "parked", "pane_id": "w1:p2",
          "pane_id_history": [], "tab_id": "w1:t1", "workspace_id": "w1", "title": "work", "cwd": "/repo",
          "argv": ["/home/u/.local/bin/claude", "--model", "haiku", "--resume", "work"],
          "label_before": "api", "note": None, "parked_mode": "keep", "layout_hint": None}
STARTED = {"type": "agent_info", "agent": {"pane_id": "w1:p2", "agent_status": "idle"}}


class ResumeTestCase(FlowTestCase):
    def setUp(self):
        super().setUp()
        self.records_dir = Path(self.environ["HERDR_PLUGIN_STATE_DIR"]) / "records"

    def park_record(self, **fields):
        records.write(self.records_dir, dict(PARKED, **fields))

    def resuming(self, **overrides):
        script = {"pane.list": {"type": "pane_list", "panes": [SHELL["pane"]]},
                  "pane.get": [SHELL, pane_reply()], "pane.process_info": SHELL_PROCESS,
                  "agent.start": STARTED, "pane.rename": {"type": "pane_info"},
                  "pane.send_input": {"type": "ok"}}
        script.update(overrides)
        return self.flow(**script)


class StartTest(ResumeTestCase):
    def test_the_session_starts_in_its_pane_with_the_replayed_flags(self):
        self.park_record()
        resume.resume(self.resuming(), UUID)
        [start] = [r for r in self.fake.requests if r["method"] == "agent.start"]
        self.assertEqual(start["params"], {"name": "parking-2716af66", "kind": "claude", "pane_id": "w1:p2",
                                           "args": ["--resume", UUID, "--model", "haiku"],
                                           "timeout_ms": 30000})


class CwdTest(ResumeTestCase):
    def test_a_different_cwd_is_entered_first(self):
        self.park_record(cwd="/work/my repo")
        resume.resume(self.resuming(), UUID)
        inputs = [r["params"] for r in self.fake.requests if r["method"] == "pane.send_input"]
        self.assertIn({"pane_id": "w1:p2", "text": "cd '/work/my repo'", "keys": ["Enter"]}, inputs)
        methods = self.fake.methods()
        self.assertLess(methods.index("pane.send_input"), methods.index("agent.start"))

    def test_the_same_cwd_sends_no_cd(self):
        self.park_record(cwd="/repo")
        resume.resume(self.resuming(), UUID)
        texts = [r["params"]["text"] for r in self.fake.requests if r["method"] == "pane.send_input"]
        self.assertFalse(any(t.startswith("cd ") for t in texts))


class NotePrintTest(ResumeTestCase):
    def test_the_note_is_printed_before_the_start(self):
        self.park_record(note="LUT の一覧を貼る前で止めた\n次は色域")
        resume.resume(self.resuming(), UUID)
        texts = [r["params"]["text"] for r in self.fake.requests if r["method"] == "pane.send_input"]
        self.assertEqual(texts, ["printf '%s\\n' '💤 LUT の一覧を貼る前で止めた' '💤 次は色域'"])
        self.assertLess(self.fake.methods().index("pane.send_input"), self.fake.methods().index("agent.start"))

    def test_a_failed_print_does_not_stop_the_resume(self):
        from tests.fake_herdr import Error
        self.park_record(note="x")
        resume.resume(self.resuming(**{"pane.send_input": Error("pane_busy")}), UUID)
        self.assertIn("agent.start", self.fake.methods())

    def test_no_note_prints_nothing(self):
        self.park_record(note=None)
        resume.resume(self.resuming(), UUID)
        self.assertNotIn("pane.send_input", self.fake.methods())


class AfterStartTest(ResumeTestCase):
    def resumed_record(self):
        path = Path(self.environ["HERDR_PLUGIN_STATE_DIR"]) / "resumed" / (UUID + ".json")
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def test_the_same_session_restores_the_label_and_moves_the_record(self):
        for label_before in ("api", None):
            with self.subTest(label_before=label_before):
                self.park_record(label_before=label_before)
                outcome = resume.resume(self.resuming(), UUID)
                self.assertEqual(outcome.kind, "resumed")
                [rename] = [r for r in self.fake.requests if r["method"] == "pane.rename"]
                self.assertEqual(rename["params"], {"pane_id": "w1:p2", "label": label_before})
                self.assertIsNone(self.saved())
                self.assertEqual(self.resumed_record()["status"], "resumed")

    def test_another_session_is_resume_failed_with_both_ids(self):
        other = "0939a1b4-2ecb-4bd4-a241-59bd6732651f"
        self.park_record()
        outcome = resume.resume(self.resuming(**{"pane.get": [SHELL, pane_reply(session_id=other)]}), UUID)
        self.assertEqual(outcome.kind, "resume_failed")
        self.assertNotIn("pane.rename", self.fake.methods())
        saved = self.saved()
        self.assertEqual(saved["status"], "resume_failed")
        self.assertIn(UUID, saved["error"])
        self.assertIn(other, saved["error"])


class NotReadyTest(ResumeTestCase):
    def test_a_start_held_by_a_dialog_is_pending_and_keeps_the_label(self):
        from tests.fake_herdr import Error
        self.park_record()
        outcome = resume.resume(self.resuming(**{"agent.start": Error("agent_not_ready", "blocked during startup")}), UUID)
        self.assertEqual(outcome.kind, "resume_pending")
        self.assertIn("answer", outcome.message)
        self.assertNotIn("pane.rename", self.fake.methods())
        self.assertEqual(self.saved()["status"], "resume_pending")


class AlreadyRunningTest(ResumeTestCase):
    def test_a_retry_after_the_dialog_only_finishes_the_resume(self):
        self.park_record(status="resume_pending")
        running = pane_reply(label="💤 work")["pane"]
        rt = self.resuming(**{"pane.list": {"type": "pane_list", "panes": [running]}})
        outcome = resume.resume(rt, UUID)
        self.assertEqual(outcome.kind, "resumed")
        self.assertNotIn("agent.start", self.fake.methods())
        [rename] = [r for r in self.fake.requests if r["method"] == "pane.rename"]
        self.assertEqual(rename["params"], {"pane_id": "w1:p2", "label": "api"})
        self.assertIsNone(self.saved())


class RunningElsewhereTest(ResumeTestCase):
    def test_a_session_already_running_in_another_pane_is_not_started_twice(self):
        self.park_record()
        parked_pane = pane_reply(agent=None, session_id=None, label="💤 work")["pane"]
        elsewhere = pane_reply(pane_id="w1:p7")["pane"]
        rt = self.resuming(**{"pane.list": {"type": "pane_list", "panes": [parked_pane, elsewhere]}})
        outcome = resume.resume(rt, UUID)
        self.assertEqual(outcome.kind, "resumed")
        self.assertNotIn("agent.start", self.fake.methods())
        [rename] = [r for r in self.fake.requests if r["method"] == "pane.rename"]
        self.assertEqual(rename["params"], {"pane_id": "w1:p2", "label": "api"})
        self.assertEqual((outcome.record["pane_id"], outcome.record["pane_id_history"]), ("w1:p7", ["w1:p2"]))


class StartTimeoutTest(ResumeTestCase):
    def test_a_start_that_times_out_keeps_the_panes_last_lines_as_the_reason(self):
        from tests.fake_herdr import Error
        self.park_record()
        tail = "\n".join("line %d" % i for i in range(1, 31))
        rt = self.resuming(**{"agent.start": Error("timeout", "timed out waiting for agent startup"),
                              "pane.read": {"type": "pane_read", "read": {"text": tail}}})
        outcome = resume.resume(rt, UUID)
        self.assertEqual(outcome.kind, "resume_failed")
        [read] = [r for r in self.fake.requests if r["method"] == "pane.read"]
        self.assertEqual(read["params"], {"pane_id": "w1:p2", "source": "recent", "lines": 10})
        saved = self.saved()
        self.assertEqual(saved["status"], "resume_failed")
        self.assertIn("timed out", saved["error"])
        self.assertIn("line 30", saved["error"])


class BusyPaneTest(ResumeTestCase):
    def test_a_pane_running_something_else_is_refused(self):
        self.park_record()
        busy = {"type": "process_info", "process_info": {"shell_pid": 100, "foreground_process_group_id": 300,
                                                         "foreground_processes": [{"pid": 300, "name": "vim"}]}}
        outcome = resume.resume(self.resuming(**{"pane.process_info": busy}), UUID)
        self.assertEqual(outcome.kind, "refused")
        self.assertIn("something else is running", outcome.message)
        self.assertNotIn("agent.start", self.fake.methods())
        self.assertNotIn("pane.send_input", self.fake.methods())
        self.assertEqual(self.saved()["status"], "parked")


class NoteAsPromptTest(ResumeTestCase):
    def test_the_note_is_sent_only_when_the_setting_asks_for_it(self):
        for enabled in (False, True):
            with self.subTest(send_note_as_prompt=enabled):
                self.settings["send_note_as_prompt"] = enabled
                self.park_record(note="continue with the colour spaces")
                resume.resume(self.resuming(**{"agent.wait": {"type": "agent_info"},
                                               "agent.prompt": {"type": "agent_prompted"}}), UUID)
                prompts = [r["params"] for r in self.fake.requests if r["method"] == "agent.prompt"]
                if not enabled:
                    self.assertEqual(prompts, [])
                    continue
                self.assertEqual(prompts, [{"target": "w1:p2", "text": "continue with the colour spaces"}])
                methods = self.fake.methods()
                self.assertLess(methods.index("agent.wait"), methods.index("agent.prompt"))
                [wait] = [r["params"] for r in self.fake.requests if r["method"] == "agent.wait"]
                self.assertEqual(wait["until"], ["idle", "done"])


class NameTest(unittest.TestCase):
    def test_the_agent_name_is_valid_for_herdr_and_comes_from_the_uuid(self):
        import re
        name = resume.agent_name(UUID)
        self.assertEqual(name, "parking-2716af66")
        self.assertRegex(name, re.compile(r"^[a-z][a-z0-9_-]{0,31}$"))


class ConfirmationTest(unittest.TestCase):
    def test_the_box_shows_the_command_the_left_out_arguments_and_the_note(self):
        record = dict(PARKED, argv=["claude", "--model", "haiku", "fix the login bug"],
                      note="LUT の一覧を貼る前で止めた\n次は色域", parked_at="2026-09-25T12:00:00Z")
        text = "\n".join(resume.confirmation(record, now=NOW))
        self.assertIn("w1:p2", text)
        self.assertIn("parked 2d ago", text)
        self.assertIn("claude --resume %s --model haiku" % UUID[:8], text)
        self.assertIn('left out: "fix the login bug"', text)
        self.assertIn("LUT の一覧を貼る前で止めた\n  次は色域", text)

    def test_nothing_left_out_says_nothing(self):
        self.assertNotIn("left out", "\n".join(resume.confirmation(dict(PARKED, argv=["claude", "-c"]), now=NOW)))


if __name__ == "__main__":
    unittest.main()
