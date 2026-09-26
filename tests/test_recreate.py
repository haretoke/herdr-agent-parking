import unittest

from agent_parking import recreate
from agent_parking.herdr_api import Pane
from tests.flows import UUID, FlowTestCase

RECORD = {"session_id": UUID, "pane_id": "w1:p9", "tab_id": "w1:t1", "workspace_id": "w1", "cwd": "/repo",
          "tab_label": "api", "workspace_label": "zf-api", "pane_id_history": []}
SPLIT = {"type": "pane_info", "pane": {"pane_id": "w1:p12", "tab_id": "w1:t1", "workspace_id": "w1"}}


def pane(pane_id, tab_id="w1:t1"):
    return Pane(pane_id=pane_id, tab_id=tab_id, workspace_id=tab_id.split(":")[0], agent=None,
                agent_status=None, cwd="/w", label=None, title=None, session_id=None)


class SiblingSecondTest(FlowTestCase):
    def test_a_second_child_is_split_off_its_sibling_and_given_its_ratio(self):
        record = dict(RECORD, layout_hint={"sibling_pane_id": "w1:p8", "position": "second",
                                           "direction": "down", "ratio": 0.7, "path": [True]})
        rt = self.flow(**{"pane.split": SPLIT, "layout.set_split_ratio": {"type": "ok"}})
        placed = recreate.place(rt, record, [pane("w1:p7"), pane("w1:p8")])
        self.assertEqual(placed.pane_id, "w1:p12")
        calls = [(r["method"], r["params"]) for r in self.fake.requests]
        self.assertEqual(calls, [
            ("pane.split", {"target_pane_id": "w1:p8", "direction": "down", "cwd": "/repo", "focus": False}),
            ("layout.set_split_ratio", {"tab_id": "w1:t1", "path": [True], "ratio": 0.7}),
        ])


class SiblingFirstTest(FlowTestCase):
    def test_a_first_child_is_swapped_into_place_before_the_ratio(self):
        record = dict(RECORD, layout_hint={"sibling_pane_id": "w1:p8", "position": "first",
                                           "direction": "right", "ratio": 0.3, "path": []})
        rt = self.flow(**{"pane.split": SPLIT, "pane.swap": {"type": "pane_swap"},
                          "layout.set_split_ratio": {"type": "ok"}})
        recreate.place(rt, record, [pane("w1:p8")])
        calls = [(r["method"], r["params"]) for r in self.fake.requests]
        self.assertEqual(calls, [
            ("pane.split", {"target_pane_id": "w1:p8", "direction": "right", "cwd": "/repo", "focus": False}),
            ("pane.swap", {"source_pane_id": "w1:p12", "target_pane_id": "w1:p8"}),
            ("layout.set_split_ratio", {"tab_id": "w1:t1", "path": [], "ratio": 0.3}),
        ])


if __name__ == "__main__":
    unittest.main()
