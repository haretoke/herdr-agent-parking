import unittest
from datetime import timedelta
from pathlib import Path

from agent_parking import config, herdr_api, park, transcript
from tests.flows import (NOW, PROCESS, SHELL, UUID, FlowRuntimeTestCase, FlowTestCase, pane_reply,
                         screen_reply)


class RefuseTest(FlowRuntimeTestCase):
    def test_only_idle_or_done_panes_can_be_parked(self):
        for status in ("working", "blocked", "unknown"):
            with self.subTest(status=status):
                rt = self.runtime({"pane.get": pane_reply(status=status)})
                outcome = park.park(rt, "w1:p2", note=None)
                self.assertEqual(outcome.kind, "refused")
                self.assertIn(status, outcome.message)
                self.assertEqual(self.fake.methods(), ["pane.get"])


class IntegrationTest(FlowRuntimeTestCase):
    def test_a_claude_pane_without_a_session_needs_the_herdr_integration(self):
        rt = self.runtime({"pane.get": pane_reply(session_id=None)})
        outcome = park.park(rt, "w1:p2", note=None)
        self.assertEqual(outcome.kind, "refused")
        self.assertIn("herdr integration install claude", outcome.message)
        self.assertEqual(self.fake.methods(), ["pane.get"])


class AgentViewTest(FlowRuntimeTestCase):
    def test_a_pane_showing_claudes_agent_view_is_refused_before_anything_is_sent(self):
        # Seen in a container: after /exit in `claude attach`, the pane showed agent view
        # while Herdr kept the session id; the park's /exit only closed the view.
        view = pane_reply()
        view["pane"]["terminal_title_stripped"] = "6 awaiting input · claude agents"
        rt = self.runtime({"pane.get": view})
        outcome = park.park(rt, "w1:p2", note=None)
        self.assertEqual(outcome.kind, "refused")
        self.assertIn("agent view", outcome.message)
        self.assertEqual(self.fake.methods(), ["pane.get"])


class DraftTest(FlowRuntimeTestCase):
    def test_a_half_typed_line_is_refused_and_no_exit_is_sent(self):
        rt = self.runtime({"pane.get": pane_reply(), "agent.read": screen_reply("❯ half typed line")})
        outcome = park.park(rt, "w1:p2", note=None)
        self.assertEqual(outcome.kind, "refused")
        self.assertIn("draft", outcome.message)
        self.assertNotIn("agent.prompt", self.fake.methods())
        read = [r for r in self.fake.requests if r["method"] == "agent.read"][0]
        self.assertEqual(read["params"], {"target": "w1:p2", "source": "visible", "format": "ansi",
                                          "strip_ansi": False})


class OrderTest(FlowTestCase):
    def test_the_record_is_on_disk_before_exit_is_sent(self):
        seen = {}

        def exit_prompt(fake, connection, reader, request):
            seen["record"] = self.saved()
            fake.reply(connection, request)

        rt = self.flow(**{"agent.prompt": exit_prompt})
        outcome = park.park(rt, "w1:p2", note=None)
        self.assertEqual(outcome.kind, "parked")
        self.assertEqual(seen["record"]["status"], "parking")
        self.assertEqual(seen["record"]["session_id"], UUID)
        self.assertLess(self.fake.methods().index("pane.process_info"), self.fake.methods().index("agent.prompt"))


class RecordFieldsTest(FlowTestCase):
    def test_what_is_read_before_exit_is_in_the_parking_record(self):
        seen = {}

        def exit_prompt(fake, connection, reader, request):
            seen["record"] = self.saved()
            fake.reply(connection, request)

        rt = self.flow(**{"agent.prompt": exit_prompt,
                          "pane.get": [pane_reply(label="api"), SHELL]})
        rt.summary_for = lambda session_id: transcript.EMPTY._replace(tokens=36890, model="claude-haiku-4-5")
        self.settings["context_window_by_model"] = {"claude-haiku": 200_000}
        outcome = park.park(rt, "w1:p2", note=None)
        before = seen["record"]
        self.assertEqual(before["argv"], ["/home/u/.local/bin/claude", "--model", "haiku"])
        self.assertEqual(before["claude_version"], "2.1.283")
        self.assertEqual(before["label_before"], "api")
        self.assertEqual(before["context_at_park"], {"tokens": 36890, "percent": 18, "compacted": False})
        self.assertEqual((before["title"], before["cwd"], before["tab_id"], before["workspace_id"]),
                         ("work", "/repo", "w1:t1", "w1"))
        self.assertEqual(before["parked_at"], "2026-09-27T12:00:00Z")
        self.assertIn("layout_hint", before)
        self.assertNotIn("parked_mode", before)
        self.assertEqual(outcome.record["parked_mode"], "keep")
        self.assertEqual(self.saved()["parked_mode"], "keep")


class ExitTest(FlowTestCase):
    def test_exit_is_a_plain_agent_prompt_without_a_wait(self):
        park.park(self.flow(), "w1:p2", note=None)
        [prompt] = [r for r in self.fake.requests if r["method"] == "agent.prompt"]
        self.assertEqual(prompt["params"], {"target": "w1:p2", "text": "/exit"})


class LabelTest(FlowTestCase):
    def test_after_the_shell_is_back_the_pane_is_labelled_and_the_old_label_kept(self):
        rt = self.flow(**{"pane.get": [pane_reply(label="api"), pane_reply(label="api"), SHELL]})
        outcome = park.park(rt, "w1:p2", note=None)
        self.assertEqual(outcome.kind, "parked")
        self.assertEqual(len(self.slept), 1)
        [rename] = [r for r in self.fake.requests if r["method"] == "pane.rename"]
        self.assertEqual(rename["params"], {"pane_id": "w1:p2", "label": "💤 work"})
        self.assertLess(self.fake.methods().index("agent.prompt"), self.fake.methods().index("pane.rename"))
        self.assertEqual(self.saved()["label_before"], "api")


class LayoutHintTest(FlowTestCase):
    def test_the_layout_hint_comes_from_the_tab_tree_before_exit(self):
        tree = {"type": "split", "direction": "right", "ratio": 0.3,
                "first": {"type": "pane", "pane_id": "w1:p1"}, "second": {"type": "pane", "pane_id": "w1:p2"}}
        rt = self.flow(**{"layout.export": {"type": "layout_export", "workspace_id": "w1", "tab_id": "w1:t1",
                                            "root": tree}})
        park.park(rt, "w1:p2", note=None)
        [export] = [r for r in self.fake.requests if r["method"] == "layout.export"]
        self.assertEqual(export["params"], {"pane_id": "w1:p2"})
        self.assertLess(self.fake.methods().index("layout.export"), self.fake.methods().index("agent.prompt"))
        self.assertEqual(self.saved()["layout_hint"], {"sibling_pane_id": "w1:p1", "position": "second",
                                                       "direction": "right", "ratio": 0.3, "path": []})

    def test_a_failing_export_leaves_no_hint_and_the_park_goes_on(self):
        outcome = park.park(self.flow(), "w1:p2", note=None)
        self.assertEqual(outcome.kind, "parked")
        self.assertIsNone(self.saved()["layout_hint"])


TWO_PANES = {"type": "layout_export", "tab_id": "w1:t1", "root": {
    "type": "split", "direction": "right", "ratio": 0.5,
    "first": {"type": "pane", "pane_id": "w1:p1"}, "second": {"type": "pane", "pane_id": "w1:p2"}}}
ONE_PANE = {"type": "layout_export", "tab_id": "w1:t1", "root": {"type": "pane", "pane_id": "w1:p2"}}


class OnParkTest(FlowTestCase):
    def test_by_default_the_pane_stays(self):
        outcome = park.park(self.flow(**{"layout.export": TWO_PANES}), "w1:p2", note=None)
        self.assertNotIn("pane.close", self.fake.methods())
        self.assertEqual(outcome.record["parked_mode"], "keep")

    def test_close_closes_the_pane_once_the_shell_alone_is_back(self):
        self.settings["on_park"] = "close"
        outcome = park.park(self.flow(**{"layout.export": TWO_PANES, "pane.close": {"type": "ok"}}),
                            "w1:p2", note=None)
        [close] = [r for r in self.fake.requests if r["method"] == "pane.close"]
        self.assertEqual(close["params"], {"pane_id": "w1:p2"})
        self.assertNotIn("pane.rename", self.fake.methods())
        self.assertEqual((outcome.kind, outcome.record["parked_mode"]), ("parked", "close"))
        self.assertEqual(self.saved()["parked_mode"], "close")

    def test_close_keeps_the_last_pane_of_a_tab_and_a_busy_pane(self):
        self.settings["on_park"] = "close"
        busy = {"type": "process_info", "process_info": {"shell_pid": 100, "foreground_process_group_id": 300,
                                                         "foreground_processes": [{"pid": 300, "name": "vim"}]}}
        for overrides, reason in [({"layout.export": ONE_PANE}, "last pane"),
                                  ({"layout.export": TWO_PANES, "pane.process_info": [PROCESS, busy]}, "shell")]:
            with self.subTest(reason=reason):
                outcome = park.park(self.flow(**overrides), "w1:p2", note=None)
                self.assertNotIn("pane.close", self.fake.methods())
                self.assertIn("pane.rename", self.fake.methods())
                self.assertEqual(outcome.record["parked_mode"], "keep")
                self.assertIn(reason, outcome.message)


class AccountTest(FlowTestCase):
    def test_the_variables_that_pick_the_account_are_recorded_and_nothing_else(self):
        # Seen on the Mac: claude-alt is claude with CLAUDE_SECURESTORAGE_CONFIG_DIR set.
        rt = self.flow()
        rt.system.environs = {200: {"CLAUDE_SECURESTORAGE_CONFIG_DIR": "/h/.claude-creds/alt", "HOME": "/h",
                                    "ANTHROPIC_API_KEY": "sk-secret"}}
        park.park(rt, "w1:p2", note=None)
        self.assertEqual(self.saved()["env"], {"CLAUDE_SECURESTORAGE_CONFIG_DIR": "/h/.claude-creds/alt"})

    def test_a_claude_whose_environment_cannot_be_read_records_none(self):
        park.park(self.flow(), "w1:p2", note=None)
        self.assertEqual(self.saved()["env"], {})


    def test_a_claude_with_its_own_config_directory_is_parked_from_a_shell_that_never_listed_it(self):
        # `park <pane>` from a shell: no list was built, so the directory is only known from
        # the process itself, and it must be known before the transcript is looked for.
        from pathlib import Path
        rt = self.flow()
        rt.system.environs = {200: {"CLAUDE_CONFIG_DIR": "/claude-work"}}
        rt.has_transcript = lambda session_id: Path("/claude-work") in rt.claude_config_dirs
        self.assertEqual(park.park(rt, "w1:p2", note=None).kind, "parked")
        self.assertEqual(self.saved()["env"], {"CLAUDE_CONFIG_DIR": "/claude-work"})


class NamedSessionTest(FlowTestCase):
    def test_a_named_session_whose_top_rule_carries_its_name_is_parked(self):
        # Seen on the Mac: "─── summit-202606 ─" above an empty box was refused as a draft.
        named = "\x1b[38;2;136;136;136m" + "─" * 60 + " summit-202606 ─\x1b[0m\r"
        text = "\r\n".join(["⏺ OK", named, "❯\xa0\r", "\x1b[38;2;136;136;136m" + "─" * 76 + "\x1b[0m\r", "  ctx 0%"])
        reply = {"type": "agent_read", "read": {"pane_id": "w1:p2", "format": "ansi", "text": text}}
        outcome = park.park(self.flow(**{"agent.read": reply}), "w1:p2", note=None)
        self.assertEqual(outcome.kind, "parked")


    def test_a_screen_without_a_readable_box_says_so_instead_of_claiming_a_draft(self):
        reply = {"type": "agent_read", "read": {"pane_id": "w1:p2", "format": "ansi", "text": "⏺ OK\r\nno box"}}
        outcome = park.park(self.flow(**{"agent.read": reply}), "w1:p2", note=None)
        self.assertEqual(outcome.kind, "refused")
        self.assertIn("could not find Claude's input box", outcome.message)
        self.assertNotIn("draft", outcome.message)


class NoConversationTest(FlowTestCase):
    def test_a_claude_that_never_had_a_conversation_is_not_parked(self):
        # Seen on the Mac: its record could not be resumed ("No conversation found").
        rt = self.flow()
        rt.has_transcript = lambda session_id: False
        outcome = park.park(rt, "w1:p2", note=None)
        self.assertEqual(outcome.kind, "refused")
        self.assertIn("no conversation yet", outcome.message)
        self.assertNotIn("agent.prompt", self.fake.methods())
        self.assertIsNone(self.saved())


def with_overlay(root):
    """The tab's layout while the dashboard's overlay (`w1:p9`) is open over it (seen on the Mac)."""
    return {"type": "layout_export", "tab_id": "w1:t1", "root": {
        "type": "split", "direction": "right", "ratio": 0.5, "first": root, "second": {"type": "pane", "pane_id": "w1:p9"}}}


class OverlayTest(FlowTestCase):
    def setUp(self):
        super().setUp()
        self.environ.update(HERDR_PANE_ID="w1:p9", HERDR_PLUGIN_ENTRYPOINT_ID="dashboard")

    def test_the_dashboards_own_pane_is_left_out_of_the_hint(self):
        park.park(self.flow(**{"layout.export": with_overlay(TWO_PANES["root"])}), "w1:p2", note=None)
        self.assertEqual(self.saved()["layout_hint"], {"sibling_pane_id": "w1:p1", "position": "second",
                                                       "direction": "right", "ratio": 0.5, "path": []})

    def test_a_pane_alone_with_the_overlay_is_the_last_one_of_its_tab(self):
        self.settings["on_park"] = "close"
        outcome = park.park(self.flow(**{"layout.export": with_overlay(ONE_PANE["root"])}), "w1:p2", note=None)
        self.assertNotIn("pane.close", self.fake.methods())
        self.assertIsNone(self.saved()["layout_hint"])
        self.assertIn("last pane", outcome.message)


class TimeoutTest(FlowTestCase):
    def test_claude_still_there_after_the_timeout_is_park_failed_and_the_pane_untouched(self):
        self.settings["exit_timeout_seconds"] = 1
        outcome = park.park(self.flow(**{"pane.get": pane_reply()}), "w1:p2", note=None)
        self.assertEqual(outcome.kind, "park_failed")
        self.assertIn("did not exit", outcome.message)
        self.assertEqual(self.saved()["status"], "park_failed")
        self.assertNotIn("pane.rename", self.fake.methods())
        self.assertNotIn("pane.close", self.fake.methods())
        self.assertEqual(sum(self.slept), 1.0)


class BlockedTest(FlowTestCase):
    def test_a_blocked_claude_refuses_the_exit_and_the_parking_record_goes(self):
        from tests.fake_herdr import Error
        rt = self.flow(**{"agent.prompt": Error("agent_blocked", "agent is waiting at a dialog")})
        outcome = park.park(rt, "w1:p2", note=None)
        self.assertEqual(outcome.kind, "refused")
        self.assertIn("dialog", outcome.message)
        self.assertIsNone(self.saved())
        self.assertNotIn("pane.rename", self.fake.methods())


class NoteTest(FlowTestCase):
    def test_the_note_is_stored_and_an_empty_one_is_null(self):
        for note, stored in [("LUT の一覧を貼る前で止めた\n次は色域", "LUT の一覧を貼る前で止めた\n次は色域"),
                             ("", None), ("  \n ", None), (None, None)]:
            with self.subTest(note=note):
                park.park(self.flow(), "w1:p2", note=note)
                self.assertEqual(self.saved()["note"], stored)


class LabelFormatTest(unittest.TestCase):
    def label(self, fmt, title):
        settings = dict(config.DEFAULTS, parked_label_format=fmt)
        return park.label(settings, {"session_id": UUID, "title": title})

    def test_the_format_is_configurable(self):
        self.assertEqual(self.label("[parked] {title} ({short_id})", "work"), "[parked] work (2716af66)")
        self.assertEqual(self.label("💤 {title}", "work"), "💤 work")

    def test_control_characters_are_dropped_and_the_label_is_cut_at_80(self):
        self.assertEqual(self.label("💤 {title}", "a\x1b[31mb\x07c"), "💤 a[31mbc")
        long = self.label("💤 {title}", "x" * 200)
        self.assertEqual(len(long), 80)

    def test_a_broken_format_falls_back_to_the_default(self):
        self.assertEqual(self.label("{nope} {title", "work"), "💤 work")


class BulkTest(unittest.TestCase):
    def test_targets_are_idle_or_done_rows_past_the_threshold_lower_bounds_included(self):
        from agent_parking.idle import Entry
        from agent_parking.inventory import Row
        rows = [Row(pane_id="w1:p1", status="idle"), Row(pane_id="w1:p2", status="done"),
                Row(pane_id="w1:p3", status="idle"), Row(pane_id="w1:p4", status="blocked"),
                Row(pane_id="w1:p5", status="working"), Row(pane_id="w1:p6", status="idle")]
        entries = {"w1:p1": Entry(1, "idle", NOW - timedelta(minutes=75), False),
                   "w1:p2": Entry(1, "done", NOW - timedelta(minutes=60), True),
                   "w1:p3": Entry(1, "idle", NOW - timedelta(minutes=59), False),
                   "w1:p4": Entry(1, "blocked", NOW - timedelta(hours=3), False),
                   "w1:p5": Entry(1, "working", NOW - timedelta(hours=3), False)}
        targets, skipped = park.bulk_targets(rows, entries, NOW, minutes=60)
        self.assertEqual([r.pane_id for r in targets], ["w1:p1", "w1:p2"])
        self.assertEqual({r.pane_id: reason for r, reason in skipped},
                         {"w1:p3": "idle 59m", "w1:p4": "blocked", "w1:p5": "working", "w1:p6": "idle time unknown"})

    def test_a_session_without_a_conversation_is_left_out_whatever_its_idle_time(self):
        from agent_parking.idle import Entry
        from agent_parking.inventory import Row
        rows = [Row(pane_id="w1:p1", status="idle", has_transcript=False)]
        entries = {"w1:p1": Entry(1, "idle", NOW - timedelta(hours=3), False)}
        targets, skipped = park.bulk_targets(rows, entries, NOW, minutes=60)
        self.assertEqual((targets, [(r.pane_id, reason) for r, reason in skipped]),
                         ([], [("w1:p1", "no conversation yet")]))

    def test_a_failure_does_not_stop_the_others_and_every_result_is_reported(self):
        calls = []

        def one(pane_id):
            calls.append(pane_id)
            if pane_id == "w1:p2":
                raise herdr_api.HerdrError("gone", "pane_not_found")
            return park.Outcome("parked", "", {"pane_id": pane_id})

        results = park.bulk_park(["w1:p1", "w1:p2", "w1:p3"], one)
        self.assertEqual(calls, ["w1:p1", "w1:p2", "w1:p3"])
        self.assertEqual([(p, o.kind) for p, o in results],
                         [("w1:p1", "parked"), ("w1:p2", "park_failed"), ("w1:p3", "parked")])
        self.assertIn("gone", results[1][1].message)


class ReparkLabelTest(FlowTestCase):
    def test_a_second_park_keeps_the_label_from_before_the_first(self):
        from agent_parking import records
        earlier = {"schema_version": 1, "session_id": UUID, "status": "parked", "pane_id": "w1:p2",
                   "title": "work", "label_before": "api", "pane_id_history": []}
        records.write(Path(self.environ["HERDR_PLUGIN_STATE_DIR"]) / "records", earlier)
        rt = self.flow(**{"pane.get": [pane_reply(label="💤 work"), SHELL]})
        park.park(rt, "w1:p2", note=None)
        self.assertEqual(self.saved()["label_before"], "api")

    def test_a_label_the_person_changed_since_is_taken_as_is(self):
        from agent_parking import records
        earlier = {"schema_version": 1, "session_id": UUID, "status": "parked", "pane_id": "w1:p2",
                   "title": "work", "label_before": "api", "pane_id_history": []}
        records.write(Path(self.environ["HERDR_PLUGIN_STATE_DIR"]) / "records", earlier)
        rt = self.flow(**{"pane.get": [pane_reply(label="new name"), SHELL]})
        park.park(rt, "w1:p2", note=None)
        self.assertEqual(self.saved()["label_before"], "new name")


class ConfirmationTest(unittest.TestCase):
    def test_the_confirmation_names_the_session_and_always_warns_about_lost_work(self):
        from agent_parking.inventory import Row
        for row in (Row(pane_id="w8:p36", name="proto_tunnel", status="idle"), Row(pane_id="w1:p2")):
            with self.subTest(row=row):
                text = "\n".join(park.confirmation(row))
                self.assertIn(row.pane_id, text)
                self.assertIn("background tasks", text)
                self.assertIn("subagents", text)


if __name__ == "__main__":
    unittest.main()
