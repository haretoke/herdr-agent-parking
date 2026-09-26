import unittest

from agent_parking import idle, inventory
from tests.fake_herdr import Error
from tests.fakes import FakeSystem
from tests.flows import PROCESS, UUID, FlowRuntimeTestCase


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
    def build(self, script, own="w1:p9", system=None):
        base = {"pane.list": pane_list(), "agent.list": {"type": "agent_list", "agents": []},
                "workspace.list": {"type": "workspace_list", "workspaces": []},
                "tab.list": {"type": "tab_list", "tabs": []},
                "pane.process_info": {"type": "process_info", "process_info": {}}}
        base.update(script)
        self.rt = self.runtime(base)
        self.rt.system = system or FakeSystem(proc=False)
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


class LabelErrorTest(BuildTestCase):
    def test_labels_that_cannot_be_read_are_left_out(self):
        got = self.build({"pane.list": pane_list(raw_pane("w1:p2")), "workspace.list": Error("internal"),
                          "tab.list": Error("internal")})
        self.assertEqual([(r.pane_id, r.tab_label, r.workspace_label) for r in got.rows], [("w1:p2", None, None)])


class ProcessTest(BuildTestCase):
    def test_memory_and_version_come_from_the_claude_process_group(self):
        system = FakeSystem(proc=False)
        system.rss = {200: 200_000, 201: 10_000}
        system.links = {"/home/u/.local/bin/claude": "/home/u/.local/share/claude/versions/2.1.290"}
        got = self.build({"pane.list": pane_list(raw_pane("w1:p2")), "pane.process_info": PROCESS}, system=system)
        [row] = got.rows
        self.assertEqual((row.rss_kb, row.claude_rss_kb, row.version, row.old), (210_000, 200_000, "2.1.283", True))


    def test_a_pane_whose_processes_cannot_be_read_keeps_its_row(self):
        got = self.build({"pane.list": pane_list(raw_pane("w1:p2")), "pane.process_info": Error("pane_not_found")})
        self.assertEqual([(r.pane_id, r.rss_kb, r.version) for r in got.rows], [("w1:p2", None, None)])


if __name__ == "__main__":
    unittest.main()
