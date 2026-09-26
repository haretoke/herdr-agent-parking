import unittest
from pathlib import Path

from agent_parking import state

DEFAULT = Path("/home/u/.local/state/herdr/plugins/haretoke.agent-parking")


class StateDirTest(unittest.TestCase):
    def test_the_plugin_state_dir_is_used_only_when_it_belongs_to_this_plugin(self):
        cases = [
            ({"HERDR_PLUGIN_ID": "haretoke.agent-parking", "HERDR_PLUGIN_STATE_DIR": "/s/mine"}, Path("/s/mine")),
            ({"HERDR_PLUGIN_ID": "other.plugin", "HERDR_PLUGIN_STATE_DIR": "/s/other"}, DEFAULT),
            ({"HERDR_PLUGIN_STATE_DIR": "/s/unknown"}, DEFAULT),
            ({"HERDR_PLUGIN_ID": "haretoke.agent-parking", "HERDR_PLUGIN_STATE_DIR": "relative"}, DEFAULT),
            ({"XDG_STATE_HOME": "/xdg"}, Path("/xdg/herdr/plugins/haretoke.agent-parking")),
            ({"XDG_STATE_HOME": "relative/state"}, DEFAULT),
            ({"XDG_STATE_HOME": ""}, DEFAULT),
            ({}, DEFAULT),
        ]
        for extra, expected in cases:
            with self.subTest(environ=extra):
                self.assertEqual(state.state_dir({"HOME": "/home/u", **extra}), expected)


class PathsTest(unittest.TestCase):
    ENV = {"HOME": "/home/u", "HERDR_PLUGIN_ID": "haretoke.agent-parking",
           "HERDR_PLUGIN_STATE_DIR": "/s"}

    def test_everything_is_in_the_state_directory_by_default(self):
        paths = state.paths(self.ENV, {"records_dir": None})
        self.assertEqual(paths.records, Path("/s/records"))
        self.assertEqual(paths.resumed, Path("/s/resumed"))
        self.assertEqual(paths.observed, Path("/s/observed.json"))
        self.assertEqual(paths.log, Path("/s/dashboard.log"))

    def test_records_dir_moves_only_the_records(self):
        for records_dir, root in [("/mnt/keep", "/mnt/keep"), ("~/.claude/parking", "/home/u/.claude/parking")]:
            with self.subTest(records_dir=records_dir):
                paths = state.paths(self.ENV, {"records_dir": records_dir})
                self.assertEqual(paths.records, Path(root) / "records")
                self.assertEqual(paths.resumed, Path(root) / "resumed")
                self.assertEqual(paths.observed, Path("/s/observed.json"))
                self.assertEqual(paths.log, Path("/s/dashboard.log"))


if __name__ == "__main__":
    unittest.main()
