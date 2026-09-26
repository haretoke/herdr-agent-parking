import unittest

from agent_parking import recreate
from agent_parking.herdr_api import Pane
from tests.flows import UUID, FlowTestCase

RECORD = {"session_id": UUID, "pane_id": "w1:p9", "tab_id": "w1:t1", "workspace_id": "w1", "cwd": "/repo",
          "tab_label": "api", "workspace_label": "zf-api", "pane_id_history": []}
SPLIT = {"type": "pane_info", "pane": {"pane_id": "w1:p12", "tab_id": "w1:t1", "workspace_id": "w1"}}


def leaf(pane_id):
    return {"type": "pane", "pane_id": pane_id}


def live(split):
    """The tab after the split, with the dashboard's overlay (`w1:p9`) open around it:
    the ratio goes to the split that holds the new pane now, wherever that is."""
    return {"type": "layout_export", "tab_id": "w1:t1", "root": {
        "type": "split", "direction": "right", "ratio": 0.5, "second": leaf("w1:p9"),
        "first": {"type": "split", "direction": "right", "ratio": 0.5, "first": leaf("w1:p7"), "second": split}}}


def pane(pane_id, tab_id="w1:t1"):
    return Pane(pane_id=pane_id, tab_id=tab_id, workspace_id=tab_id.split(":")[0], agent=None,
                agent_status=None, cwd="/w", label=None, title=None, session_id=None)


class SiblingSecondTest(FlowTestCase):
    def test_a_second_child_is_split_off_its_sibling_and_given_its_ratio(self):
        record = dict(RECORD, layout_hint={"sibling_pane_id": "w1:p8", "position": "second",
                                           "direction": "down", "ratio": 0.7, "path": [True]})
        after = live({"type": "split", "direction": "down", "ratio": 0.5, "first": leaf("w1:p8"),
                      "second": leaf("w1:p12")})
        rt = self.flow(**{"pane.split": SPLIT, "layout.export": after, "layout.set_split_ratio": {"type": "ok"}})
        placed = recreate.place(rt, record, [pane("w1:p7"), pane("w1:p8")])
        self.assertEqual(placed.pane_id, "w1:p12")
        calls = [(r["method"], r["params"]) for r in self.fake.requests]
        self.assertEqual(calls, [
            ("pane.split", {"target_pane_id": "w1:p8", "direction": "down", "cwd": "/repo", "focus": False}),
            ("layout.export", {"pane_id": "w1:p12"}),
            ("layout.set_split_ratio", {"tab_id": "w1:t1", "path": [False, True], "ratio": 0.7}),
        ])


class SiblingFirstTest(FlowTestCase):
    def test_a_first_child_is_swapped_into_place_before_the_ratio(self):
        record = dict(RECORD, layout_hint={"sibling_pane_id": "w1:p8", "position": "first",
                                           "direction": "right", "ratio": 0.3, "path": []})
        after = live({"type": "split", "direction": "right", "ratio": 0.5, "first": leaf("w1:p12"),
                      "second": leaf("w1:p8")})
        rt = self.flow(**{"pane.split": SPLIT, "pane.swap": {"type": "pane_swap"}, "layout.export": after,
                          "layout.set_split_ratio": {"type": "ok"}})
        recreate.place(rt, record, [pane("w1:p8")])
        calls = [(r["method"], r["params"]) for r in self.fake.requests]
        self.assertEqual(calls, [
            ("pane.split", {"target_pane_id": "w1:p8", "direction": "right", "cwd": "/repo", "focus": False}),
            ("pane.swap", {"source_pane_id": "w1:p12", "target_pane_id": "w1:p8"}),
            ("layout.export", {"pane_id": "w1:p12"}),
            ("layout.set_split_ratio", {"tab_id": "w1:t1", "path": [False, True], "ratio": 0.3}),
        ])


class TabTest(FlowTestCase):
    def test_without_a_sibling_pane_a_pane_of_the_same_tab_is_split_right(self):
        hints = [{"sibling_pane_id": None, "position": "first", "direction": "right", "ratio": 0.3, "path": []},
                 {"sibling_pane_id": "w1:p5", "position": "second", "direction": "down", "ratio": 0.5, "path": []},
                 None]
        for hint in hints:
            with self.subTest(hint=hint):
                rt = self.flow(**{"pane.split": SPLIT})
                placed = recreate.place(rt, dict(RECORD, layout_hint=hint), [pane("w2:p1", "w2:t1"), pane("w1:p7")])
                self.assertEqual(placed.pane_id, "w1:p12")
                calls = [(r["method"], r["params"]) for r in self.fake.requests]
                self.assertEqual(calls, [("pane.split", {"target_pane_id": "w1:p7", "direction": "right",
                                                         "cwd": "/repo", "focus": False})])


    def test_the_dashboards_own_pane_is_never_split_for_it(self):
        self.environ.update(HERDR_PANE_ID="w1:p9", HERDR_PLUGIN_ENTRYPOINT_ID="dashboard")
        old_hint = {"sibling_pane_id": "w1:p9", "position": "first", "direction": "right", "ratio": 0.5, "path": []}
        rt = self.flow(**{"pane.split": SPLIT})
        recreate.place(rt, dict(RECORD, layout_hint=old_hint), [pane("w1:p9"), pane("w1:p7")])
        calls = [(r["method"], r["params"]) for r in self.fake.requests]
        self.assertEqual(calls, [("pane.split", {"target_pane_id": "w1:p7", "direction": "right",
                                                 "cwd": "/repo", "focus": False})])


class WorkspaceTest(FlowTestCase):
    def test_without_the_tab_a_new_tab_opens_in_the_workspace(self):
        created = {"type": "tab_created", "tab": {"tab_id": "w1:t9"}, "root_pane": {"pane_id": "w1:p20"}}
        rt = self.flow(**{"tab.create": created})
        placed = recreate.place(rt, dict(RECORD, layout_hint=None), [pane("w1:p3", "w1:t4")])
        self.assertEqual(placed.pane_id, "w1:p20")
        calls = [(r["method"], r["params"]) for r in self.fake.requests]
        self.assertEqual(calls, [("tab.create", {"workspace_id": "w1", "cwd": "/repo", "label": "api",
                                                 "focus": False})])


class NewWorkspaceTest(FlowTestCase):
    def test_without_the_workspace_a_new_one_needs_a_yes_first(self):
        created = {"type": "workspace_created", "workspace": {"workspace_id": "w5"},
                   "tab": {"tab_id": "w5:t1"}, "root_pane": {"pane_id": "w5:p1"}}
        rt = self.flow(**{"workspace.create": created})
        asked = recreate.place(rt, dict(RECORD, layout_hint=None), [pane("w2:p1", "w2:t1")])
        self.assertIsNone(asked.pane_id)
        self.assertEqual(asked.message, recreate.NEEDS_WORKSPACE)
        self.assertEqual(self.fake.requests, [])
        placed = recreate.place(rt, dict(RECORD, layout_hint=None), [pane("w2:p1", "w2:t1")], new_workspace=True)
        self.assertEqual(placed.pane_id, "w5:p1")
        [(method, params)] = [(r["method"], r["params"]) for r in self.fake.requests]
        self.assertEqual((method, params), ("workspace.create", {"cwd": "/repo", "label": "zf-api", "focus": False}))


class NoCwdTest(FlowTestCase):
    def test_without_a_cwd_nothing_is_created(self):
        for cwd in (None, ""):
            with self.subTest(cwd=cwd):
                placed = recreate.place(self.flow(), dict(RECORD, cwd=cwd), [pane("w1:p7")], new_workspace=True)
                self.assertIsNone(placed.pane_id)
                self.assertIn("cwd", placed.message)
                self.assertEqual(self.fake.requests, [])


if __name__ == "__main__":
    unittest.main()
