import json
import unittest
import unittest.mock
from datetime import timedelta

from agent_parking import idle, inventory, records, state, terminal, times, transcript
from tests.fake_herdr import Error
from tests.fakes import FakeSystem
from tests.flows import NOW, PROCESS, UUID, FlowRuntimeTestCase


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
        self.rt.summary_for = lambda session_id: getattr(self, "summaries", {}).get(session_id)
        self.tracker = idle.Tracker(self.rt.clock)
        return inventory.build(self.rt, self.tracker, own)

    def park(self, session_id, pane_id, title, days, status="parked"):
        records.write(state.paths(self.environ, self.settings).records, {
            "schema_version": 1, "session_id": session_id, "status": status, "pane_id": pane_id,
            "pane_id_history": [], "tab_id": "w1:t1", "workspace_id": "w1", "title": title, "cwd": "/notes",
            "argv": ["claude"], "label_before": None, "parked_at": times.iso(NOW - timedelta(days=days))})


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
                          "tab.list": Error("internal"), "agent.list": Error("internal")})
        self.assertEqual([(r.pane_id, r.tab_label, r.workspace_label) for r in got.rows], [("w1:p2", None, None)])


class ProcessTest(BuildTestCase):
    def test_memory_and_version_come_from_the_claude_process_group(self):
        system = FakeSystem(proc=False)
        system.rss = {200: 200_000, 201: 10_000}
        system.links = {"/home/u/.local/bin/claude": "/home/u/.local/share/claude/versions/2.1.290"}
        got = self.build({"pane.list": pane_list(raw_pane("w1:p2")), "pane.process_info": PROCESS}, system=system)
        [row] = got.rows
        self.assertEqual((row.rss_kb, row.claude_rss_kb, row.version, row.old), (210_000, 200_000, "2.1.283", True))
        self.assertEqual(row.current_version, "2.1.290")


    def test_a_pane_whose_processes_cannot_be_read_keeps_its_row(self):
        got = self.build({"pane.list": pane_list(raw_pane("w1:p2")), "pane.process_info": Error("pane_not_found")})
        self.assertEqual([(r.pane_id, r.rss_kb, r.version) for r in got.rows], [("w1:p2", None, None)])


class CtxTest(BuildTestCase):
    def test_ctx_comes_from_the_sessions_transcript_and_the_window(self):
        self.settings["context_window_by_model"] = {"claude-haiku": 200_000}
        summary = transcript.Summary(tokens=37_000, model="claude-haiku-4-5", compacted=False, compacted_at=None,
                                     last_activity=None)
        base = {"pane.list": pane_list(raw_pane("w1:p2"), raw_pane("w1:p3", session_id=None))}
        self.summaries = {UUID: summary}
        got = self.build(base)
        self.assertEqual([r.ctx for r in got.rows], ["37k 18%", ""])


class IdleTest(BuildTestCase):
    def test_idle_time_comes_from_the_tracker_fed_by_agent_list(self):
        self.summaries = {UUID: transcript.EMPTY._replace(last_activity=NOW - timedelta(minutes=72))}
        agents = [{"pane_id": "w1:p2", "state_change_seq": 4, "agent_status": "idle"},
                  {"pane_id": "w1:p3", "state_change_seq": 9, "agent_status": "working"}]
        got = self.build({"pane.list": pane_list(raw_pane("w1:p2"), raw_pane("w1:p3", status="working"),
                                                 raw_pane("w1:p4", session_id=None)),
                          "agent.list": {"type": "agent_list", "agents": agents}})
        self.assertEqual([r.idle for r in got.rows], ["1h12m", "—", "≥0m"])
        self.assertEqual((self.tracker.entries["w1:p2"].seq, self.tracker.entries["w1:p3"].seq), (4, 9))


OTHER = "5e0c1f2a-0000-4000-8000-000000000001"
THIRD = "5e0c1f2a-0000-4000-8000-000000000002"


class ParkedRowsTest(BuildTestCase):
    def test_parked_records_follow_the_live_rows_and_those_without_a_pane_come_last(self):
        self.park(THIRD, "w1:p8", "billing", 5)
        self.park(OTHER, "w1:p5", "color notes", 2)
        got = self.build({"pane.list": pane_list(raw_pane("w1:p2"), raw_pane("w1:p5", agent=None, session_id=None,
                                                                             label="💤 color notes"))})
        self.assertEqual([(r.pane_id, r.status, r.name, r.cwd, r.idle, r.session_id) for r in got.rows], [
            ("w1:p2", "idle", "work", "/repo", "≥0m", UUID),
            ("w1:p5", "parked", "color notes", "/notes", "2d", OTHER),
            (None, "parked", "billing", "/notes", "5d", THIRD)])
        self.assertEqual([r.record is not None for r in got.rows], [False, True, True])
        self.assertEqual(got.rows[1].tab_id, "w1:t1")


class ResumedByHandTest(BuildTestCase):
    def test_a_session_resumed_by_hand_elsewhere_settles_its_record_and_gets_no_parked_row(self):
        self.park(OTHER, "w1:p5", "color notes", 2)
        got = self.build({"pane.list": pane_list(raw_pane("w1:p5", agent=None, session_id=None, label="💤 color notes"),
                                                 raw_pane("w1:p6", session_id=OTHER)),
                          "pane.rename": {"type": "pane_info"}})
        self.assertEqual([(r.pane_id, r.status, r.record) for r in got.rows], [("w1:p6", "idle", None)])
        [rename] = [r["params"] for r in self.fake.requests if r["method"] == "pane.rename"]
        self.assertEqual(rename, {"pane_id": "w1:p5", "label": None})
        paths = state.paths(self.environ, self.settings)
        self.assertIsNone(records.read(paths.records, OTHER))
        self.assertEqual(records.read(paths.resumed, OTHER)["pane_id"], "w1:p6")


class SettledElsewhereTest(BuildTestCase):
    def test_a_record_another_dashboard_settled_since_the_listing_is_left_alone(self):
        self.park(OTHER, "w1:p5", "color notes", 2)
        directory = state.paths(self.environ, self.settings).records
        listed = records.list_records(directory)
        (directory / (OTHER + ".json")).unlink()  # the other dashboard moved it meanwhile
        with unittest.mock.patch.object(records, "list_records", return_value=listed):
            got = self.build({"pane.list": pane_list(raw_pane("w1:p5", session_id=OTHER)),
                              "pane.rename": {"type": "pane_info"}})
        self.assertEqual([(r.pane_id, r.status) for r in got.rows], [("w1:p5", "idle")])


class ConflictTest(BuildTestCase):
    def test_another_session_in_the_records_pane_is_a_conflict_row_and_the_record_stays(self):
        self.park(OTHER, "w1:p5", "color notes", 2)
        got = self.build({"pane.list": pane_list(raw_pane("w1:p5"))})
        self.assertEqual([(r.pane_id, r.status, r.session_id) for r in got.rows],
                         [("w1:p5", "idle", UUID), ("w1:p5", "conflict", OTHER)])
        self.assertIsNotNone(records.read(state.paths(self.environ, self.settings).records, OTHER))


class RecordStatusTest(BuildTestCase):
    def test_every_record_is_listed_with_a_short_status(self):
        ids = ["5e0c1f2a-0000-4000-8000-00000000001%d" % n for n in range(5)]
        for session_id, status in zip(ids, ["parking", "park_failed", "resume_pending", "resume_failed"]):
            self.park(session_id, None, status, 1, status=status)
        self.park(ids[2], "w1:p5", "pending", 1, status="resume_pending")
        (state.paths(self.environ, self.settings).records / (ids[4] + ".json")).write_text("{broken")
        got = self.build({"pane.list": pane_list(raw_pane("w1:p5", session_id=None))})
        self.assertEqual([(r.pane_id, r.status, r.session_id) for r in got.rows], [
            ("w1:p5", "idle", None), ("w1:p5", "pending", ids[2]), (None, "parking", ids[0]),
            (None, "failed", ids[1]), (None, "failed", ids[3]), (None, "broken", ids[4])])


    def test_a_park_in_progress_or_a_failed_park_is_not_settled_by_its_running_session(self):
        for status, shown in (("parking", "parking"), ("park_failed", "failed")):
            with self.subTest(status=status):
                self.park(OTHER, "w1:p5", "notes", 1, status=status)
                got = self.build({"pane.list": pane_list(raw_pane("w1:p5", session_id=OTHER))})
                self.assertEqual([(r.pane_id, r.status) for r in got.rows], [("w1:p5", "idle"), ("w1:p5", shown)])
                self.assertEqual(records.read(state.paths(self.environ, self.settings).records, OTHER)["status"],
                                 status)


class PollAgainTest(BuildTestCase):
    def test_a_second_build_shows_the_new_status_memory_ctx_and_a_longer_idle_time(self):
        now = [NOW]
        system = FakeSystem(proc=False)
        system.rss = {200: 200_000}
        self.summaries = {UUID: transcript.EMPTY._replace(tokens=37_000)}
        first = self.build({"pane.list": [pane_list(raw_pane("w1:p2")), pane_list(raw_pane("w1:p2")),
                                          pane_list(raw_pane("w1:p2", status="working"))],
                            "agent.list": {"type": "agent_list", "agents": [{"pane_id": "w1:p2", "state_change_seq": 4}]},
                            "pane.process_info": PROCESS}, system=system).rows[0]
        self.rt.clock = self.tracker.clock = lambda: now[0]
        self.assertEqual((first.status, first.rss_kb, first.ctx, first.idle), ("idle", 200_000, "37k", "≥0m"))

        now[0] += timedelta(minutes=5)
        second = inventory.build(self.rt, self.tracker, "w1:p9").rows[0]
        self.assertEqual(second.idle, "≥5m")

        now[0] += timedelta(minutes=1)
        system.rss[200] = 260_000
        self.summaries[UUID] = transcript.EMPTY._replace(tokens=52_000)
        self.fake.script["agent.list"] = {"type": "agent_list", "agents": [{"pane_id": "w1:p2", "state_change_seq": 5}]}
        third = inventory.build(self.rt, self.tracker, "w1:p9").rows[0]
        self.assertEqual((third.status, third.rss_kb, third.ctx, third.idle), ("working", 260_000, "52k", "—"))


class SaveObservedTest(BuildTestCase):
    def test_each_refresh_saves_the_idle_tracking_of_the_live_panes(self):
        self.build({"pane.list": [pane_list(raw_pane("w1:p2"), raw_pane("w1:p3")), pane_list(raw_pane("w1:p2"))]})
        refresh = terminal.refresher(self.rt, self.tracker, "w1:p9")
        refresh()
        saved = json.loads(self.rt.paths.observed.read_text())
        self.assertEqual(list(saved), ["w1:p2"])
        self.assertEqual(saved["w1:p2"]["status"], "idle")


if __name__ == "__main__":
    unittest.main()
