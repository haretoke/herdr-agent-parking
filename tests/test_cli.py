import json
import tempfile
import unittest
from pathlib import Path

from agent_parking import cli, state


class CliTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name)


class ConfigTest(CliTestCase):
    def test_the_plugin_reads_config_json_from_its_config_dir_and_logs_problems(self):
        config_dir, state_dir = self.home / "config", self.home / "state"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(json.dumps({"poll_seconds": 5, "bogus": 1}))
        rt = cli.make_runtime({"HOME": str(self.home), "HERDR_PLUGIN_ID": state.PLUGIN_ID,
                               "HERDR_PLUGIN_CONFIG_DIR": str(config_dir), "HERDR_PLUGIN_STATE_DIR": str(state_dir),
                               "HERDR_SOCKET_PATH": "/nonexistent.sock"})
        self.assertEqual(rt.settings["poll_seconds"], 5)
        self.assertIn("bogus", (state_dir / "dashboard.log").read_text())

    def test_a_shell_subcommand_reads_the_same_file_through_the_xdg_path(self):
        config_dir = self.home / ".config" / "herdr" / "plugins" / "config" / state.PLUGIN_ID
        config_dir.mkdir(parents=True)
        (config_dir / "config.json").write_text(json.dumps({"on_park": "close"}))
        rt = cli.make_runtime({"HOME": str(self.home), "HERDR_PLUGIN_ID": "other.plugin",
                               "HERDR_SOCKET_PATH": "/nonexistent.sock"})
        self.assertEqual(rt.settings["on_park"], "close")


if __name__ == "__main__":
    unittest.main()
