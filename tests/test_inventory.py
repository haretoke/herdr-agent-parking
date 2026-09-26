import unittest
from datetime import datetime, timedelta, timezone

from agent_parking import inventory, records, transcript
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
        self.rss = {}
        self.links = {}
        self.found = {}

    def realpath(self, path):
        return self.links.get(path, path)

    def which(self, command, path):
        return self.found.get(command)

    def rss_kb(self, pid):
        return self.rss.get(pid)

    def cmdline(self, pid):
        return self.cmdlines.get(pid)

    def exe(self, pid):
        return self.exes.get(pid)

    def has_proc(self):
        return self.proc


class MemoryTest(unittest.TestCase):
    def test_the_group_sum_and_the_claude_share(self):
        info = ProcessInfo(5, 63115, [{"pid": 63115}, {"pid": 97490}, {"pid": 97556}])
        fake = FakeSystem()
        fake.rss = {63115: 365_000, 97490: 8_000, 97556: 9_000}
        self.assertEqual(inventory.memory(info, fake), (382_000, 365_000))

    def test_unknown_members_are_skipped_and_nothing_known_is_none(self):
        info = ProcessInfo(5, 63115, [{"pid": 63115}, {"pid": 97490}])
        fake = FakeSystem()
        fake.rss = {97490: 8_000}
        self.assertEqual(inventory.memory(info, fake), (8_000, None))
        fake.rss = {}
        self.assertEqual(inventory.memory(info, fake), (None, None))


class CurrentVersionTest(unittest.TestCase):
    ENV = {"HOME": "/home/u", "PATH": "/usr/bin:/home/u/.local/bin"}

    def fake(self, links, found=None):
        fake = FakeSystem()
        fake.links = links
        fake.found = found or {}
        return fake

    def test_a_path_argv0_then_claude_command_on_path_then_the_home_install(self):
        links = {"/Users/u/.local/bin/claude": "/Users/u/.local/share/claude/versions/2.1.283",
                 "/home/u/.local/bin/claude": "/home/u/.local/share/claude/versions/2.1.282",
                 "/opt/claude/bin/claude": "/opt/claude/versions/2.1.290"}
        fake = self.fake(links, found={"claude": "/opt/claude/bin/claude"})
        settings = {"claude_command": "claude"}
        self.assertEqual(inventory.current_version("/Users/u/.local/bin/claude", settings, fake, self.ENV), "2.1.283")
        self.assertEqual(inventory.current_version("claude", settings, fake, self.ENV), "2.1.290")
        fake.found = {}
        self.assertEqual(inventory.current_version("claude", settings, fake, self.ENV), "2.1.282")

    def test_nothing_that_looks_like_a_version_is_unknown(self):
        fake = self.fake({"/usr/local/bin/claude": "/usr/local/lib/node_modules/@anthropic-ai/claude-code/cli.js"})
        self.assertIsNone(inventory.current_version("/usr/local/bin/claude", {"claude_command": "claude"}, fake, self.ENV))
        self.assertIsNone(inventory.current_version(None, {"claude_command": "claude"}, self.fake({}), self.ENV))

    def test_old_only_when_both_versions_are_known_and_differ(self):
        self.assertTrue(inventory.is_old("2.1.281", "2.1.283"))
        self.assertFalse(inventory.is_old("2.1.283", "2.1.283"))
        self.assertFalse(inventory.is_old(None, "2.1.283"))
        self.assertFalse(inventory.is_old("2.1.281", None))


class CtxTextTest(unittest.TestCase):
    NOW = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)

    def summary(self, tokens=None, compacted=False, compacted_at=None, model="claude-haiku"):
        return transcript.Summary(tokens=tokens, model=model, compacted=compacted,
                                  compacted_at=compacted_at, last_activity=None)

    def test_tokens_with_and_without_a_percentage(self):
        self.assertEqual(inventory.ctx_text(self.summary(36890), 200_000, self.NOW), "37k 18%")
        self.assertEqual(inventory.ctx_text(self.summary(36890), None, self.NOW), "37k")
        self.assertEqual(inventory.ctx_text(self.summary(850), 200_000, self.NOW), "850 0%")

    def test_a_compacted_session_shows_how_long_ago(self):
        at = self.NOW - timedelta(hours=2)
        self.assertEqual(inventory.ctx_text(self.summary(compacted=True, compacted_at=at), 200_000, self.NOW),
                         "compacted 2h")
        self.assertEqual(inventory.ctx_text(self.summary(compacted=True), 200_000, self.NOW), "compacted")

    def test_nothing_known_is_empty(self):
        self.assertEqual(inventory.ctx_text(transcript.EMPTY, 200_000, self.NOW), "")
        self.assertEqual(inventory.ctx_text(None, None, self.NOW), "")


OTHER = "0939a1b4-2ecb-4bd4-a241-59bd6732651f"


def parked(session_id=UUID, pane_id="w1:p2", status="parked"):
    return {"schema_version": 1, "session_id": session_id, "pane_id": pane_id, "status": status,
            "label_before": None, "pane_id_history": []}


class ReconcileTest(unittest.TestCase):
    def test_the_same_session_running_in_the_records_pane_was_resumed_by_hand(self):
        panes = [pane("w1:p2", session_id=UUID, label="💤 work")]
        [decision] = inventory.reconcile([parked()], panes)
        self.assertEqual((decision.kind, decision.pane_id, decision.restore_label_on), ("resumed", "w1:p2", "w1:p2"))


class ReconcileElsewhereTest(unittest.TestCase):
    def test_the_session_running_in_another_pane_moves_the_record_there(self):
        panes = [pane("w1:p2", agent=None, session_id=None, label="💤 work"), pane("w1:p7", session_id=UUID)]
        [decision] = inventory.reconcile([parked(pane_id="w1:p2")], panes)
        self.assertEqual((decision.kind, decision.pane_id, decision.restore_label_on), ("resumed", "w1:p7", "w1:p2"))
        moved = records.with_pane(decision.record, decision.pane_id)
        self.assertEqual((moved["pane_id"], moved["pane_id_history"]), ("w1:p7", ["w1:p2"]))

    def test_no_label_to_restore_when_the_original_pane_is_gone(self):
        [decision] = inventory.reconcile([parked(pane_id="w1:p2")], [pane("w1:p7", session_id=UUID)])
        self.assertEqual((decision.pane_id, decision.restore_label_on), ("w1:p7", None))


class ReconcileConflictTest(unittest.TestCase):
    def test_another_session_in_the_records_pane_is_a_conflict_and_the_record_stays(self):
        [decision] = inventory.reconcile([parked(pane_id="w1:p2")], [pane("w1:p2", session_id=OTHER)])
        self.assertEqual((decision.kind, decision.pane_id, decision.restore_label_on), ("conflict", "w1:p2", None))


class ReconcileParkedTest(unittest.TestCase):
    def test_a_record_with_its_pane_is_parked_and_without_it_has_no_pane(self):
        panes = [pane("w1:p2", agent=None, session_id=None, label="💤 work")]
        decisions = inventory.reconcile([parked(pane_id="w1:p2"), parked(OTHER, pane_id="w1:p9")], panes)
        self.assertEqual([(d.kind, d.pane_id) for d in decisions], [("parked", "w1:p2"), ("no_pane", None)])

    def test_every_record_gets_exactly_one_decision_in_order(self):
        panes = [pane("w1:p2", session_id=UUID), pane("w1:p3", session_id=OTHER)]
        third = "a528d90c-d0d6-404a-a9ee-373de7435e3c"
        decisions = inventory.reconcile([parked(pane_id="w1:p2"), parked(third, pane_id="w1:p3"),
                                         parked(OTHER, pane_id="w1:p9")], panes)
        self.assertEqual([d.kind for d in decisions], ["resumed", "conflict", "resumed"])


class OtherAgentsTest(unittest.TestCase):
    def test_agents_other_than_claude_are_counted_for_the_footer(self):
        panes = [pane("w1:p1"), pane("w1:p2", agent="codex"), pane("w1:p3", agent="codex"),
                 pane("w1:p4", agent="opencode"), pane("w1:p5", agent=None)]
        self.assertEqual(inventory.other_agents(panes), {"codex": 2, "opencode": 1})


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
