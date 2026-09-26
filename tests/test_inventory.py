import unittest

from agent_parking import inventory
from agent_parking.herdr_api import Pane

UUID = "2716af66-e4d8-4950-8185-97da891f78a9"


def pane(pane_id, agent="claude", status="idle", session_id=UUID, **fields):
    base = dict(pane_id=pane_id, tab_id=pane_id.split(":")[0] + ":t1", workspace_id=pane_id.split(":")[0],
                agent=agent, agent_status=status, cwd="/w", label=None, title="work", session_id=session_id)
    base.update(fields)
    return Pane(**base)


class ClaudePanesTest(unittest.TestCase):
    def test_only_claude_panes_other_than_the_dashboard_itself(self):
        panes = [pane("w1:p1"), pane("w1:p2", agent="codex"), pane("w1:p3", agent=None),
                 pane("w1:p4"), pane("w1:p9")]
        self.assertEqual([p.pane_id for p in inventory.claude_panes(panes, own_pane_id="w1:p9")],
                         ["w1:p1", "w1:p4"])
        self.assertEqual(len(inventory.claude_panes(panes, own_pane_id=None)), 3)


class RowTest(unittest.TestCase):
    def test_a_row_carries_place_name_cwd_status_and_session(self):
        p = pane("w8:p36", tab_id="w8:t3", workspace_id="w8", label="api", title="proto_tunnel", cwd="/repo",
                 status="done")
        row = inventory.row(p, workspace_labels={"w8": "zf-api"}, tab_labels={"w8:t3": "2"})
        self.assertEqual((row.pane_id, row.tab_id, row.workspace_id), ("w8:p36", "w8:t3", "w8"))
        self.assertEqual((row.workspace_label, row.tab_label, row.label), ("zf-api", "2", "api"))
        self.assertEqual((row.name, row.cwd, row.status, row.session_id), ("proto_tunnel", "/repo", "done", UUID))

    def test_unknown_labels_stay_empty(self):
        row = inventory.row(pane("w1:p1"), workspace_labels={}, tab_labels={})
        self.assertEqual((row.workspace_label, row.tab_label), (None, None))


if __name__ == "__main__":
    unittest.main()
