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


if __name__ == "__main__":
    unittest.main()
