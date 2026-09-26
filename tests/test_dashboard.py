import unittest

from agent_parking import dashboard, display, park, table
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


if __name__ == "__main__":
    unittest.main()
