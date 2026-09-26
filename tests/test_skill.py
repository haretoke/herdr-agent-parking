import re
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
SKILL = REPOSITORY / "skills" / "prepare-compact" / "SKILL.md"


class SkillTest(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_the_skill_is_named_for_the_command_the_dashboard_sends(self):
        front = re.match(r"---\n(.*?)\n---\n", self.text, re.S)
        self.assertIsNotNone(front)
        self.assertIn("name: prepare-compact", front.group(1))
        self.assertIn("/prepare-compact", front.group(1))

    def test_the_steps_save_report_clean_up_and_end_with_the_focus_tag_but_never_compact(self):
        words = " ".join(self.text.split())
        for part in ("memory", "uncommitted changes and unpushed commits", "Clean up",
                     "Never stop or delete anything you did not start", "<compact-focus>...</compact-focus>",
                     "even when nothing needed saving", "You cannot run `/compact` yourself"):
            with self.subTest(part=part):
                self.assertIn(part, words)


if __name__ == "__main__":
    unittest.main()
