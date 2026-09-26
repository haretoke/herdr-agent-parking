import unittest
import unittest.mock

from agent_parking import actions, idle, park
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


if __name__ == "__main__":
    unittest.main()
