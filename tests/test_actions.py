import unittest

from agent_parking import actions, idle
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


if __name__ == "__main__":
    unittest.main()
