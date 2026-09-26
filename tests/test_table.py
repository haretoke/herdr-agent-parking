import unittest

from agent_parking import table

FULL = ("place", "name", "status", "idle", "ctx", "rss", "ver")
WITHOUT_VER_RSS = ("place", "name", "status", "idle", "ctx")
SHORT = ("place_id", "name", "status", "idle", "ctx_short")
NARROW = ("place_id", "name", "status")


class ColumnsTest(unittest.TestCase):
    def test_low_priority_columns_go_first_as_the_pane_narrows(self):
        cases = [(120, FULL), (78, FULL), (77, WITHOUT_VER_RSS), (64, WITHOUT_VER_RSS),
                 (63, SHORT), (52, SHORT), (51, NARROW), (20, NARROW)]
        for width, expected in cases:
            with self.subTest(width=width):
                self.assertEqual(table.columns(width), expected)


if __name__ == "__main__":
    unittest.main()
