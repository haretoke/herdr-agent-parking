import tempfile
import unittest
from pathlib import Path

from agent_parking import presence


class PresenceTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "state" / "dashboard.json"

    def test_an_announced_dashboard_is_current_while_its_process_lives(self):
        presence.announce(self.path, "w1:p9", 4242, "overlay")
        self.assertEqual(presence.current(self.path, alive=lambda pid: pid == 4242),
                         {"pane_id": "w1:p9", "pid": 4242, "placement": "overlay"})
        self.assertIsNone(presence.current(self.path, alive=lambda pid: False))

    def test_nothing_announced_or_a_broken_file_is_no_dashboard(self):
        self.assertIsNone(presence.current(self.path, alive=lambda pid: True))
        self.path.parent.mkdir(parents=True)
        for text in ("{", "[]", '{"pane_id": "w1:p9"}'):
            with self.subTest(text=text):
                self.path.write_text(text)
                self.assertIsNone(presence.current(self.path, alive=lambda pid: True))

    def test_a_dashboard_withdraws_only_its_own_announcement(self):
        presence.announce(self.path, "w1:p9", 4242, "tab")
        presence.release(self.path, "w1:p3")  # an older dashboard that was replaced
        self.assertTrue(self.path.exists())
        presence.release(self.path, "w1:p9")
        self.assertFalse(self.path.exists())
        presence.release(self.path, "w1:p9")  # already gone: nothing to do


if __name__ == "__main__":
    unittest.main()
