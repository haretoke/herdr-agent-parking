import unittest

from agent_parking import inventory
from agent_parking.herdr_api import Pane, ProcessInfo

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


class ClaudeProcessTest(unittest.TestCase):
    def test_the_claude_process_is_the_foreground_group_leader(self):
        info = ProcessInfo(shell_pid=5, group_id=63115, processes=[
            {"pid": 97556, "name": "node", "argv0": "chrome-devtools-mcp"},
            {"pid": 63115, "name": "2.1.283", "argv": ["/home/u/.local/bin/claude"]},
            {"pid": 97490, "name": "node"}])
        self.assertEqual(inventory.claude_process(info)["pid"], 63115)

    def test_no_leader_among_the_processes_gives_none(self):
        self.assertIsNone(inventory.claude_process(ProcessInfo(5, None, [{"pid": 7}])))
        self.assertIsNone(inventory.claude_process(ProcessInfo(5, 9, [{"pid": 7}])))


class FakeSystem:
    def __init__(self, cmdlines=None, exes=None, proc=True):
        self.cmdlines = cmdlines or {}
        self.exes = exes or {}
        self.proc = proc

    def cmdline(self, pid):
        return self.cmdlines.get(pid)

    def exe(self, pid):
        return self.exes.get(pid)

    def has_proc(self):
        return self.proc


class RunningVersionTest(unittest.TestCase):
    def test_linux_reads_the_exe_link_and_macos_the_process_name(self):
        linux = FakeSystem(exes={7: "/home/node/.local/share/claude/versions/2.1.281"})
        self.assertEqual(inventory.running_version({"pid": 7, "name": "claude"}, linux), "2.1.281")
        mac = FakeSystem(proc=False)
        self.assertEqual(inventory.running_version({"pid": 7, "name": "2.1.283"}, mac), "2.1.283")

    def test_anything_that_does_not_look_like_a_version_is_unknown(self):
        cases = [
            ({"pid": 7, "name": "claude"}, FakeSystem(proc=False)),
            ({"pid": 7, "name": "node"}, FakeSystem(exes={7: "/usr/bin/node"})),
            ({"pid": 7, "name": "2.1.283"}, FakeSystem(exes={})),
        ]
        for process, fake in cases:
            with self.subTest(process=process):
                self.assertIsNone(inventory.running_version(process, fake))


class ArgvTest(unittest.TestCase):
    def test_argv_from_process_info_then_proc_cmdline_then_empty(self):
        linux = FakeSystem({7: ["claude", "--resume", "review-all"]})
        self.assertEqual(inventory.argv_of({"pid": 7, "argv": ["/b/claude", "-c"]}, linux), ["/b/claude", "-c"])
        self.assertEqual(inventory.argv_of({"pid": 7, "name": "claude"}, linux), ["claude", "--resume", "review-all"])
        self.assertEqual(inventory.argv_of({"pid": 9, "name": "claude"}, linux), [])


if __name__ == "__main__":
    unittest.main()
