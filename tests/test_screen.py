import unittest

from agent_parking import screen

RULE = "\x1b[38;5;244m" + "─" * 40 + "\x1b[0m"


def box(line, below=RULE):
    return "\r\n".join(["⏺ SEVEN", "", RULE, line, below, "  ctx ⣶··· 18% │ Haiku 4.5"])


class InputBoxTest(unittest.TestCase):
    def test_the_box_between_the_rules_is_read_with_its_styling(self):
        cases = [
            (box("❯"), "empty"),
            (box("❯ "), "empty"),
            (box("❯ \x1b[0m\x1b[2mTry \"create a util logging.py that...\"\x1b[0m\r"), "empty"),
            (box("❯ half typed line"), "draft"),
            (box("❯ typed text\r"), "draft"),
            (box("❯ \x1b[1mbold draft\x1b[0m"), "draft"),
            (box("❯ \x1b[2mdim\x1b[0m and typed"), "draft"),
            ("⏺ no box here\r\nplain output", "unknown"),
            (box("❯", below="not a rule"), "unknown"),
            (box("❯\xa0\r").replace(RULE, "\x1b[38;5;244m" + "─" * 40 + " summit-202606 ─\x1b[0m", 1), "empty"),
            (box("❯ typed").replace(RULE, "─" * 40 + " summit-202606 ─", 1), "draft"),
            (box("❯", below="── not a rule"), "unknown"),
            ("\r\n".join(["❯ Reply with just the word SEVEN.", "⏺ SEVEN", RULE, "❯", RULE]), "empty"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(screen.input_box(text), expected)


if __name__ == "__main__":
    unittest.main()
