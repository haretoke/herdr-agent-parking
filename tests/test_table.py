import unittest

from agent_parking import display, table
from agent_parking.inventory import Row

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


class NameWidthTest(unittest.TestCase):
    def test_the_name_takes_what_the_other_columns_leave_but_at_least_12(self):
        cases = [(120, 56), (78, 14), (77, 31), (64, 18), (63, 24), (52, 13), (51, 27), (36, 12), (20, 12)]
        for width, name in cases:
            with self.subTest(width=width):
                self.assertEqual(table.widths(table.columns(width), width)["name"], name)


def live(**fields):
    base = dict(pane_id="w8:p36", tab_id="w8:t3", workspace_id="w8", tab_label="2", workspace_label="zf-api",
                label="web", name="api gateway refactor", status="idle", rss_kb=210_000, version="2.1.283",
                ctx="37k 18%")
    base.update(fields)
    return Row(**base)


class CellsTest(unittest.TestCase):
    def test_a_live_row_gives_every_column_its_text(self):
        cells = table.cells(live(idle="≥1h12m"))
        self.assertEqual(cells, {"place": "w8/t3/p36 web", "place_id": "w8/t3/p36", "name": "api gateway refactor",
                                 "status": "idle", "idle": "≥1h12m", "ctx": "37k 18%", "ctx_short": "37k",
                                 "rss": "205M", "ver": "2.1.283", "old": ""})

    def test_the_place_label_is_the_pane_then_the_tab_then_the_workspace_label(self):
        self.assertEqual(table.cells(live(label=None))["place"], "w8/t3/p36 2")
        self.assertEqual(table.cells(live(label=None, tab_label=None))["place"], "w8/t3/p36 zf-api")
        self.assertEqual(table.cells(live(label=None, tab_label=None, workspace_label=None))["place"],
                         "w8/t3/p36")

    def test_parked_and_paneless_rows_show_the_mark_and_no_memory(self):
        parked = table.cells(live(status="parked", rss_kb=None, version=None, record={}, idle="2d"))
        self.assertEqual((parked["place"], parked["place_id"], parked["rss"], parked["ver"]),
                         ("w8/t3/p36 💤", "w8/t3/p36 💤", "—", ""))
        paneless = table.cells(Row(status="parked", name="billing", record={}, idle="5d"))
        self.assertEqual((paneless["place"], paneless["place_id"]), ("(no pane) 💤", "(no pane) 💤"))

    def test_short_ctx_keeps_the_tokens_or_the_compaction_age(self):
        for ctx, short in [("37k 18%", "37k"), ("37k", "37k"), ("compacted 2h", "cmp 2h"),
                           ("compacted", "cmp"), ("", "")]:
            with self.subTest(ctx=ctx):
                self.assertEqual(table.cells(live(ctx=ctx))["ctx_short"], short)

    def test_memory_in_megabytes_then_gigabytes_and_old_versions_marked(self):
        self.assertEqual(table.cells(live(rss_kb=1_300_000))["rss"], "1.2G")
        self.assertEqual(table.cells(live(rss_kb=None))["rss"], "")
        self.assertEqual(table.cells(live(version="2.1.281", old=True))["ver"], "2.1.281 old")


class LineTest(unittest.TestCase):
    def test_a_row_is_drawn_in_its_columns_and_never_wider_than_the_pane(self):
        cells = table.cells(live(idle="≥1h12m"))
        self.assertEqual(table.line(cells, 78, selected=True),
                         "▶ w8/t3/p36 web  api gateway r… idle     ≥1h12m 37k 18%      205M  2.1.283")
        self.assertEqual(table.line(cells, 51, selected=False), "  w8/t3/p36    api gateway refactor        idle")
        for width in (120, 78, 77, 64, 63, 52, 51, 36, 20):
            with self.subTest(width=width):
                self.assertLessEqual(display.width(table.line(cells, width, selected=False)), width)


class OldMarkTest(unittest.TestCase):
    def test_an_old_session_keeps_a_mark_beside_its_status_when_ver_is_dropped(self):
        cells = table.cells(live(version="2.1.281", old=True, idle="12m"))
        self.assertIn(" idle ", table.line(cells, 78, selected=False))
        self.assertIn("2.1.281 old", table.line(cells, 78, selected=False))
        for width in (77, 52, 51):
            with self.subTest(width=width):
                self.assertIn(" idle!", table.line(cells, width, selected=False))
        current = table.cells(live(idle="12m"))
        self.assertNotIn("!", table.line(current, 60, selected=False))


class HeaderTest(unittest.TestCase):
    def test_the_titles_sit_above_their_columns(self):
        self.assertEqual(table.header(78), "  place" + " " * 10 + "name" + " " * 11 + "status   idle   ctx" + " " * 10 +
                         "rss   ver")
        self.assertEqual(table.header(51), "  place" + " " * 8 + "name" + " " * 24 + "status")


class DetailTest(unittest.TestCase):
    def test_the_detail_line_shows_what_was_dropped_and_the_note(self):
        old = table.cells(live(version="2.1.281", old=True, idle="≥1h12m"))
        self.assertEqual(table.detail(old, None, 78), "")
        self.assertEqual(table.detail(old, None, 70), "    ↳ 205M · 2.1.281 old")
        self.assertEqual(table.detail(old, None, 60), "    ↳ web · 37k 18% · 205M · 2.1.281 old")
        self.assertEqual(table.detail(old, None, 51), "    ↳ web · idle ≥1h12m · 37k 18% · 205M · 2.1.281…")
        parked = table.cells(live(status="parked", rss_kb=None, version=None, record={}, idle="2d"))
        self.assertEqual(table.detail(parked, "stopped before the wiki\nthen push", 100),
                         '    ↳ "stopped before the wiki"')


if __name__ == "__main__":
    unittest.main()
