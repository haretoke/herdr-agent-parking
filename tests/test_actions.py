import os
import unittest
import unittest.mock

from agent_parking import actions, idle, park, records
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


if __name__ == "__main__":
    unittest.main()
