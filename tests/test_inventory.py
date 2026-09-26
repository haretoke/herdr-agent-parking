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


if __name__ == "__main__":
    unittest.main()
