import unittest

from agent_parking import idle, inventory
from tests.fakes import FakeSystem
from tests.flows import UUID, FlowRuntimeTestCase


def raw_pane(pane_id, agent="claude", status="idle", session_id=UUID, label=None, title="work"):
    workspace = pane_id.split(":")[0]
    pane = {"pane_id": pane_id, "tab_id": workspace + ":t1", "workspace_id": workspace, "agent": agent,
            "agent_status": status, "cwd": "/repo", "label": label, "terminal_title_stripped": title}
    if session_id:
        pane["agent_session"] = {"agent": agent, "kind": "id", "value": session_id}
    return pane


def pane_list(*panes):
    return {"type": "pane_list", "panes": list(panes)}


class BuildTestCase(FlowRuntimeTestCase):
    def build(self, script, own="w1:p9"):
        base = {"pane.list": pane_list(), "agent.list": {"type": "agent_list", "agents": []},
                "workspace.list": {"type": "workspace_list", "workspaces": []},
                "tab.list": {"type": "tab_list", "tabs": []},
                "pane.process_info": {"type": "process_info", "process_info": {}}}
        base.update(script)
        self.rt = self.runtime(base)
        self.rt.system = FakeSystem(proc=False)
        self.tracker = idle.Tracker(self.rt.clock, lambda pane_id: None)
        return inventory.build(self.rt, self.tracker, own)


class BuildRowsTest(BuildTestCase):
    def test_claude_panes_become_rows_with_their_labels_and_other_agents_are_counted(self):
        panes = pane_list(raw_pane("w1:p2", label="api"), raw_pane("w1:p3", agent="codex", session_id=None),
                          raw_pane("w1:p4", agent="codex"), raw_pane("w1:p9"),
                          raw_pane("w1:p5", agent=None, session_id=None))
        got = self.build({"pane.list": panes,
                          "workspace.list": {"type": "workspace_list",
                                             "workspaces": [{"workspace_id": "w1", "label": "zf-api"}]},
                          "tab.list": {"type": "tab_list", "tabs": [{"tab_id": "w1:t1", "label": "2"}]}})
        self.assertEqual([(r.pane_id, r.label, r.tab_label, r.workspace_label, r.status, r.session_id)
                          for r in got.rows], [("w1:p2", "api", "2", "zf-api", "idle", UUID)])
        self.assertEqual(got.others, {"codex": 2})


if __name__ == "__main__":
    unittest.main()
