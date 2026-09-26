import unittest

from agent_parking import display


class CellTest(unittest.TestCase):
    def test_control_characters_are_dropped(self):
        self.assertEqual(display.cell("a\x1b[31mb\x07c\td\x7fe\u009bf", 20), "a[31mbcdef")

    def test_text_is_cut_to_the_width_with_cjk_counting_double(self):
        cases = [
            ("proto_tunnel", 20, "proto_tunnel"),
            ("proto_tunnel 圧縮とクリーン", 20, "proto_tunnel 圧縮と…"),
            ("圧縮とクリーン", 6, "圧縮…"),
            ("abc", 3, "abc"),
            ("abcd", 3, "ab…"),
            ("", 5, ""),
        ]
        for text, width, expected in cases:
            with self.subTest(text=text, width=width):
                got = display.cell(text, width)
                self.assertEqual(got, expected)
                self.assertLessEqual(display.width(got), width)

    def test_width_counts_wide_characters_twice(self):
        self.assertEqual(display.width("aあＡ"), 5)


if __name__ == "__main__":
    unittest.main()
