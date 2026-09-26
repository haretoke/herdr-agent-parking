import unittest

from agent_parking import dashboard, display, table
from agent_parking.inventory import Inventory, Row


def live(pane_id="w8:p36", **fields):
    base = dict(pane_id=pane_id, tab_id="w8:t3", workspace_id="w8", label="web", name="api gateway refactor",
                status="idle", rss_kb=210_000, version="2.1.283", ctx="37k 18%", idle="12m")
    base.update(fields)
    return Row(**base)


def board(*rows, others=None):
    shown = dashboard.Dashboard(refresh=lambda: Inventory(list(rows), others or {}))
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


if __name__ == "__main__":
    unittest.main()
