import os
import unittest
import unittest.mock

from agent_parking import actions, idle, park, records, resume
from tests.flows import UUID
from tests.flows import FlowRuntimeTestCase


class ActionsTestCase(FlowRuntimeTestCase):
    def actions(self, **script):
        rt = self.runtime(script)
        return actions.Actions(rt, idle.Tracker(rt.clock))


class FocusTest(ActionsTestCase):
    def test_focus_asks_herdr_to_focus_the_pane(self):
        acting = self.actions(**{"pane.focus": {"type": "ok"}})
        acting.focus("w1:p2")
        self.assertEqual([(r["method"], r["params"]) for r in self.fake.requests],
                         [("pane.focus", {"pane_id": "w1:p2"})])


class FlowsTest(ActionsTestCase):
    def test_park_runs_the_park_flow_on_the_runtime(self):
        acting = self.actions()
        with unittest.mock.patch.object(park, "park", return_value="outcome") as flow:
            self.assertEqual(acting.park("w1:p2", "wiki"), "outcome")
        flow.assert_called_once_with(acting.rt, "w1:p2", "wiki")


class ForgetTest(ActionsTestCase):
    def test_forget_deletes_the_record_and_leaves_the_transcript(self):
        acting = self.actions()
        records.write(acting.rt.paths.records, {"schema_version": 1, "session_id": UUID, "status": "parked"})
        transcript = self.tmp.name + "/.claude/projects/-repo/%s.jsonl" % UUID
        os.makedirs(os.path.dirname(transcript))
        with open(transcript, "w") as f:
            f.write("{}\n")
        acting.forget(UUID)
        self.assertIsNone(records.read(acting.rt.paths.records, UUID))
        self.assertTrue(os.path.exists(transcript))


class SetNoteTest(ActionsTestCase):
    def test_the_note_is_rewritten_in_the_record_and_blank_means_none(self):
        acting = self.actions()
        records.write(acting.rt.paths.records, {"schema_version": 1, "session_id": UUID, "status": "parked",
                                                "note": "old", "title": "work"})
        acting.set_note(UUID, "wiki\ntable")
        self.assertEqual(records.read(acting.rt.paths.records, UUID)["note"], "wiki\ntable")
        self.assertEqual(records.read(acting.rt.paths.records, UUID)["title"], "work")
        acting.set_note(UUID, "  ")
        self.assertIsNone(records.read(acting.rt.paths.records, UUID)["note"])


class ResumeTest(ActionsTestCase):
    def test_resume_runs_the_resume_flow_and_now_is_the_runtimes_clock(self):
        acting = self.actions()
        with unittest.mock.patch.object(resume, "resume", return_value="outcome") as flow:
            self.assertEqual(acting.resume(UUID, True), "outcome")
        flow.assert_called_once_with(acting.rt, UUID, new_workspace=True)
        self.assertEqual(acting.now(), acting.rt.clock())


class SwapTest(ActionsTestCase):
    def test_swap_runs_the_swap_flow(self):
        acting = self.actions()
        with unittest.mock.patch.object(resume, "swap", return_value=("parked", "resumed")) as flow:
            self.assertEqual(acting.swap("w1:p2"), ("parked", "resumed"))
        flow.assert_called_once_with(acting.rt, "w1:p2")


if __name__ == "__main__":
    unittest.main()
