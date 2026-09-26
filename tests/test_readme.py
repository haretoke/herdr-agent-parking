import unittest
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


class ReadmeTest(unittest.TestCase):
    def setUp(self):
        self.words = " ".join(README.read_text(encoding="utf-8").split())

    def test_the_readme_explains_copying_the_skill_and_recommends_compact_instructions(self):
        for part in ("cp -R skills/prepare-compact ~/.claude/skills/", "## Compact Instructions", "CLAUDE.md"):
            with self.subTest(part=part):
                self.assertIn(part, self.words)

    def test_the_readme_shows_how_to_bind_the_action_to_a_key(self):
        self.assertIn('command = "haretoke.agent-parking.open"', self.words)


if __name__ == "__main__":
    unittest.main()
