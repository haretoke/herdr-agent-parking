import unittest
from datetime import datetime, timezone

from agent_parking import compact, dashboard, display, park, recreate, resume, table, transcript
from agent_parking.inventory import Inventory, Row


def live(pane_id="w8:p36", **fields):
    base = dict(pane_id=pane_id, tab_id="w8:t3", workspace_id="w8", label="web", name="api gateway refactor",
                status="idle", rss_kb=210_000, version="2.1.283", ctx="37k 18%", idle="12m")
    base.update(fields)
    return Row(**base)


class FakeActions:
    """Records what the dashboard asks for; answers with the outcomes given."""

    def __init__(self, **outcomes):
        self.calls = []
        self.outcomes = outcomes

    def __getattr__(self, name):
        def action(*args):
            self.calls.append((name,) + args)
            return self.outcomes.get(name)
        return action


def board(*rows, others=None, actions=None):
    shown = dashboard.Dashboard(refresh=lambda: Inventory(list(rows), others or {}), actions=actions)
    shown.refresh()
    return shown


class ScreenTest(unittest.TestCase):
    def test_the_screen_has_a_title_the_table_and_the_keys(self):
        first, second = live(), live("w8:p37", name="docs cleanup", status="working", idle="—")
        lines = board(first, second, others={"codex": 5}).lines(78, 20)
        self.assertEqual(lines[0], " Agent parking · 2 claude · 410M · codex: 5 (not managed)")
        self.assertEqual(lines[1], " " + "─" * 76)
        self.assertEqual(lines[2], table.header(78))
        self.assertEqual(lines[3], table.line(table.cells(first), 78, selected=True))
        self.assertEqual(lines[4], table.line(table.cells(second), 78, selected=False))
        self.assertEqual(lines[5], lines[1])
        self.assertTrue(lines[6].startswith(" s park  c compact  C compact+park  r resume"), lines[6])
        self.assertEqual(len(lines), 7)
        for line in lines:
            self.assertLessEqual(display.width(line), 78)


class DetailTest(unittest.TestCase):
    def test_the_selected_row_has_its_detail_line_and_i_toggles_it(self):
        first = live()
        parked = live("w8:p37", status="parked", record={"note": "stopped before the wiki"}, idle="2d")
        shown = board(first, parked)
        lines = shown.lines(60, 20)
        self.assertEqual(lines[4], table.detail(table.cells(first), None, 60))
        self.assertEqual(lines[5], table.line(table.cells(parked), 60, selected=False))
        shown.on_input(b"i")
        self.assertEqual(shown.lines(60, 20)[4], lines[5])
        shown.on_input(b"i")
        self.assertEqual(shown.lines(60, 20), lines)

    def test_a_parked_row_shows_its_note_and_nothing_is_added_when_there_is_nothing_to_say(self):
        parked = live(status="parked", record={"note": "stopped before the wiki"}, idle="2d")
        lines = board(parked, live("w8:p37")).lines(100, 20)
        self.assertEqual(lines[4], '    ↳ "stopped before the wiki"')
        self.assertEqual(len(board(live()).lines(100, 20)), 6)


class MoveTest(unittest.TestCase):
    def test_j_k_and_the_arrows_move_the_selection_and_stop_at_the_ends(self):
        shown = board(live("w8:p1"), live("w8:p2"), live("w8:p3"))
        steps = [(b"k", 0), (b"j", 1), (b"\x1b[B", 2), (b"j", 2), (b"\x1b[A", 1), (b"kk", 0)]
        for data, selected in steps:
            with self.subTest(data=data):
                shown.on_input(data)
                self.assertEqual(shown.selected, selected)
        self.assertEqual(board().selected, 0)
        board().on_input(b"j")


class HeightTest(unittest.TestCase):
    def test_the_list_fits_the_height_and_scrolls_to_keep_the_selection_in_view(self):
        rows = [live("w8:p%d" % n, name="session %d" % n) for n in range(10)]
        shown = board(*rows)
        lines = shown.lines(78, 10)
        self.assertEqual(len(lines), 10)
        self.assertIn("session 0", lines[3])
        self.assertTrue(lines[-1].startswith(" s park"))
        for _ in range(9):
            shown.on_input(b"j")
        lines = shown.lines(78, 10)
        self.assertEqual(len(lines), 10)
        self.assertTrue(any("▶" in line and "session 9" in line for line in lines), lines)
        shown.on_input(b"k")
        self.assertTrue(any("▶" in line and "session 8" in line for line in shown.lines(78, 10)))
        self.assertIn("session 9", "".join(shown.lines(78, 10)))  # no jump back to the top


class KeepSelectionTest(unittest.TestCase):
    def test_the_selection_follows_its_session_when_a_refresh_reorders_the_rows(self):
        a = live("w8:p1", session_id="a")
        b = live("w8:p2", session_id="b")
        c = live("w8:p3", session_id="c")
        parked_b = live("w8:p2", session_id="b", status="parked", record={})
        inventories = [Inventory([a, b, c], {}), Inventory([a, c, parked_b], {}), Inventory([a], {})]
        shown = dashboard.Dashboard(refresh=lambda: inventories.pop(0))
        shown.refresh()
        shown.on_input(b"j")
        shown.refresh()
        self.assertEqual(shown.selected, 2)  # b moved to the parked block
        shown.refresh()
        self.assertEqual(shown.selected, 0)  # gone: the nearest row that is left


class GoTest(unittest.TestCase):
    def test_g_moves_to_the_selected_pane_and_closes_the_dashboard(self):
        actions = FakeActions()
        shown = board(live("w8:p1"), live("w8:p2"), actions=actions)
        shown.on_input(b"jg")
        self.assertEqual(actions.calls, [("focus", "w8:p2")])
        self.assertTrue(shown.quit)

    def test_g_on_a_row_without_a_pane_says_so_and_stays(self):
        actions = FakeActions()
        shown = board(Row(name="billing", status="parked", record={}), actions=actions)
        shown.on_input(b"g")
        self.assertEqual(actions.calls, [])
        self.assertFalse(shown.quit)
        self.assertIn("no pane", shown.lines(78, 20)[-2])


class ParkRefusedTest(unittest.TestCase):
    def test_s_on_a_row_that_cannot_be_parked_says_why_and_does_nothing(self):
        cases = [(live(status="working"), "working"), (live(status="blocked"), "blocked"),
                 (live(status="unknown"), "unknown"), (live(status="parked", record={}), "already parked")]
        for row, reason in cases:
            with self.subTest(status=row.status):
                actions = FakeActions()
                shown = board(row, actions=actions)
                shown.on_input(b"s")
                self.assertIn(reason, shown.message)
                self.assertIsNone(shown.dialog)
                self.assertEqual(actions.calls, [])


class ParkTest(unittest.TestCase):
    def test_s_asks_for_a_note_then_parks_after_showing_the_wait_and_reads_the_list_again(self):
        refreshes = []
        actions = FakeActions(park=park.Outcome("parked", "", {}))
        shown = dashboard.Dashboard(refresh=lambda: refreshes.append(1) or Inventory([live()], {}), actions=actions)
        shown.refresh()
        shown.on_input(b"s")
        lines = shown.lines(78, 24)
        text = " ".join(line.strip() for line in lines)
        self.assertIn('park w8:p36 "api gateway refactor"', text)
        self.assertIn("do not come back on resume.", text)  # wrapped, not cut
        self.assertEqual(lines[-1], " > ")
        self.assertTrue(all(display.width(line) <= 78 for line in lines))
        shown.on_input(b"wiki\r\r")
        self.assertEqual(actions.calls, [])  # not yet: the loop runs it once the wait is drawn
        self.assertIn("parking w8:p36", shown.lines(78, 24)[-2])
        shown.run_pending()
        self.assertEqual(actions.calls, [("park", "w8:p36", "wiki")])
        self.assertEqual(len(refreshes), 2)
        self.assertIn("parked w8:p36", shown.lines(78, 24)[-2])

    def test_esc_in_the_note_parks_nothing(self):
        actions = FakeActions()
        shown = board(live(), actions=actions)
        shown.on_input(b"s")
        shown.on_input(b"\x1b")
        self.assertIsNone(shown.dialog)
        self.assertIsNone(shown.pending)
        self.assertEqual(actions.calls, [])


class ForgetTest(unittest.TestCase):
    def test_x_forgets_the_record_after_a_yes(self):
        parked = live(session_id="s1", status="parked", record={"session_id": "s1"})
        actions = FakeActions()
        shown = board(parked, actions=actions)
        shown.on_input(b"x")
        self.assertIn("(y/N)", shown.lines(78, 24)[-1])
        shown.on_input(b"n")
        self.assertEqual((shown.dialog, actions.calls), (None, []))
        shown.on_input(b"xy")
        shown.run_pending()
        self.assertEqual(actions.calls, [("forget", "s1")])

    def test_x_on_a_live_row_has_nothing_to_forget(self):
        shown = board(live(), actions=FakeActions())
        shown.on_input(b"x")
        self.assertIsNone(shown.dialog)
        self.assertIn("no record", shown.message)


class NoteTest(unittest.TestCase):
    def test_n_edits_the_note_starting_from_the_current_one(self):
        parked = live(session_id="s1", status="parked", record={"session_id": "s1", "note": "wiki"})
        actions = FakeActions()
        shown = board(parked, actions=actions)
        shown.on_input(b"n")
        self.assertEqual(shown.lines(78, 24)[-1], " > wiki")
        shown.on_input(b" table\r\r")
        shown.run_pending()
        self.assertEqual(actions.calls, [("set_note", "s1", "wiki table")])

    def test_n_on_a_live_row_has_no_record(self):
        shown = board(live(), actions=FakeActions())
        shown.on_input(b"n")
        self.assertIsNone(shown.dialog)


class FilterTest(unittest.TestCase):
    def test_slash_filters_by_name_cwd_and_labels_ignoring_case(self):
        rows = [live("w8:p1", name="API gateway", cwd="/w/one", label=None),
                live("w8:p2", name="docs", cwd="/w/api-docs", label=None),
                live("w8:p3", name="infra", cwd="/w/infra", label=None, tab_label="Api"),
                live("w8:p4", name="release", cwd="/w/rel", label=None)]
        shown = board(*rows)
        shown.on_input(b"jjj/api\r")
        self.assertEqual([row.pane_id for row in shown.visible()], ["w8:p1", "w8:p2", "w8:p3"])
        self.assertIn("filter: api", shown.lines(78, 24)[0])
        self.assertEqual(shown.selected, 2)
        shown.on_input(b"/\x15\r")  # Ctrl-U clears it
        self.assertEqual(len(shown.visible()), 4)
        self.assertNotIn("filter", shown.lines(78, 24)[0])

    def test_esc_keeps_the_filter_as_it_was(self):
        shown = board(live("w8:p1", name="api"), live("w8:p2", name="docs"))
        shown.on_input(b"/docs\r/x\x1b")
        self.assertEqual([row.pane_id for row in shown.visible()], ["w8:p2"])


UUID = "2716af66-e4d8-4950-8185-97da891f78a9"
NOW = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
RECORD = {"session_id": UUID, "pane_id": "w8:p36", "title": "api", "cwd": "/repo",
          "argv": ["claude", "--effort", "medium"], "note": "wiki\ntable", "parked_at": "2026-09-25T12:00:00Z"}


def acted(actions):
    return [call for call in actions.calls if call[0] != "now"]


class ResumeTest(unittest.TestCase):
    def test_r_shows_the_whole_note_and_the_command_then_enter_resumes(self):
        actions = FakeActions(resume=resume.Outcome("resumed", "", RECORD), now=NOW)
        shown = board(live(session_id=UUID, status="parked", record=RECORD), actions=actions)
        shown.on_input(b"r")
        text = "\n".join(shown.lines(78, 30))
        for part in ("parked 2d ago", "claude --resume 2716af66 --effort medium", "  wiki", "  table",
                     "Enter to resume"):
            self.assertIn(part, text)
        shown.on_input(b"\r")
        shown.run_pending()
        self.assertEqual(acted(actions), [("resume", UUID, False)])
        self.assertIn("resumed w8:p36", shown.message)

    def test_esc_returns_to_the_list(self):
        actions = FakeActions(now=NOW)
        shown = board(live(session_id=UUID, status="parked", record=RECORD), actions=actions)
        shown.on_input(b"r\x1b")
        self.assertEqual((shown.dialog, shown.pending, acted(actions)), (None, None, []))


class NewWorkspaceTest(unittest.TestCase):
    def test_a_resume_that_needs_a_new_workspace_asks_then_resumes_with_it(self):
        refused = resume.Outcome("refused", recreate.NEEDS_WORKSPACE, RECORD)
        actions = FakeActions(resume=refused, now=NOW)
        shown = board(live(session_id=UUID, status="parked", record=RECORD), actions=actions)
        shown.on_input(b"r\r")
        shown.run_pending()
        self.assertIn("(y/N)", shown.lines(78, 30)[-1])
        actions.outcomes["resume"] = resume.Outcome("resumed", "", dict(RECORD, pane_id="w5:p1"))
        shown.on_input(b"y")
        shown.run_pending()
        self.assertEqual(acted(actions), [("resume", UUID, False), ("resume", UUID, True)])
        self.assertIn("resumed w5:p1", shown.message)


class ResumeNoteTest(unittest.TestCase):
    def test_e_edits_the_note_and_comes_back_to_the_confirmation(self):
        actions = FakeActions(now=NOW)
        shown = board(live(session_id=UUID, status="parked", record=RECORD), actions=actions)
        shown.on_input(b"re")
        self.assertEqual(shown.lines(78, 30)[-2:], [" > wiki", " > table"])
        shown.on_input(b" done\r\r")
        self.assertEqual(acted(actions), [("set_note", UUID, "wiki\ntable done")])
        self.assertIn("  table done", "\n".join(shown.lines(78, 30)))
        self.assertIn("Enter to resume", shown.lines(78, 30)[-1])


class SwapTest(unittest.TestCase):
    def test_R_on_an_old_session_parks_and_resumes_at_once(self):
        parked = park.Outcome("parked", "", {"session_id": UUID})
        actions = FakeActions(swap=(parked, resume.Outcome("resumed", "", {"pane_id": "w8:p36"})))
        shown = board(live(version="2.1.281", current_version="2.1.283", old=True), actions=actions)
        shown.on_input(b"R")
        self.assertIn("swapping w8:p36", shown.lines(78, 24)[-2])
        shown.run_pending()
        self.assertEqual(actions.calls, [("swap", "w8:p36")])
        self.assertIn("resumed w8:p36", shown.message)

    def test_R_on_a_session_already_on_the_current_version_asks_first(self):
        actions = FakeActions(swap=(park.Outcome("refused", "Claude is typing", None), None))
        shown = board(live(version="2.1.283", current_version="2.1.283"), actions=actions)
        shown.on_input(b"R")
        self.assertIn("already runs 2.1.283", " ".join(shown.lines(78, 24)[-2:]))
        shown.on_input(b"n")
        self.assertEqual((shown.pending, actions.calls), (None, []))
        shown.on_input(b"Ry")
        shown.run_pending()
        self.assertEqual(actions.calls, [("swap", "w8:p36")])
        self.assertIn("refused w8:p36: Claude is typing", shown.message)

    def test_R_on_a_working_row_is_refused(self):
        shown = board(live(status="working"), actions=FakeActions())
        shown.on_input(b"R")
        self.assertIn("working", shown.message)


REPLY = transcript.Reply(found=True, text="Saved the port map to memory.\n<compact-focus>port map</compact-focus>",
                         focus="port map")


class CompactTest(unittest.TestCase):
    def test_c_prepares_shows_the_report_and_focus_then_compacts_with_it(self):
        actions = FakeActions(prepare=compact.Outcome("prepared", "", REPLY),
                              compact=compact.Outcome("compacted", "", None))
        shown = board(live(), actions=actions)
        shown.on_input(b"c")
        self.assertIn("preparing w8:p36", shown.lines(78, 24)[-2])
        shown.run_pending()
        text = "\n".join(shown.lines(78, 30))
        self.assertIn("Saved the port map to memory.", text)
        self.assertIn("focus: port map", text)
        shown.on_input(b"\r")
        self.assertIn("compacting w8:p36", shown.lines(78, 24)[-2])
        shown.run_pending()
        self.assertEqual(actions.calls, [("prepare", "w8:p36"), ("compact", "w8:p36", "port map")])
        self.assertIn("compacted w8:p36", shown.message)


    def test_e_edits_the_focus_and_an_empty_one_sends_compact_alone(self):
        actions = FakeActions(prepare=compact.Outcome("prepared", "", REPLY),
                              compact=compact.Outcome("compacted", "", None))
        shown = board(live(), actions=actions)
        shown.on_input(b"c")
        shown.run_pending()
        shown.on_input(b"e")
        self.assertEqual(shown.lines(78, 30)[-1], " > port map")
        shown.on_input(b" and TODOs\r")
        self.assertIn("focus: port map and TODOs", "\n".join(shown.lines(78, 30)))
        shown.on_input(b"e\x15\r\r")
        shown.run_pending()
        self.assertEqual(actions.calls[-1], ("compact", "w8:p36", None))

    def test_a_preparation_that_stops_says_why_and_compacts_nothing(self):
        blocked = compact.Outcome("blocked", "Claude stopped at a dialog while preparing", None)
        actions = FakeActions(prepare=blocked)
        shown = board(live(), actions=actions)
        shown.on_input(b"c")
        shown.run_pending()
        self.assertIsNone(shown.dialog)
        self.assertIn("blocked w8:p36: Claude stopped at a dialog", shown.message)


if __name__ == "__main__":
    unittest.main()
