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


UUID = "2716af66-e4d8-4950-8185-97da891f78a9"


class TranscriptWiringTest(CliTestCase):
    def test_the_runtime_reads_transcripts_under_the_claude_config_dir_and_the_statusline_windows(self):
        project = self.home / ".claude" / "projects" / "-repo"
        project.mkdir(parents=True)
        usage = {"input_tokens": 1000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 36000}
        rows = [{"type": "user", "timestamp": "2026-09-27T11:00:00Z", "message": {"content": "hi"}},
                {"type": "assistant", "timestamp": "2026-09-27T11:00:05Z",
                 "message": {"model": "claude-haiku-4-5", "usage": usage}}]
        (project / (UUID + ".jsonl")).write_text("".join(json.dumps(row) + "\n" for row in rows))
        state_dir = self.home / "state"
        state_dir.mkdir()
        (state_dir / "context-windows.json").write_text(json.dumps({UUID: 200000}))
        rt = cli.make_runtime({"HOME": str(self.home), "HERDR_PLUGIN_ID": state.PLUGIN_ID,
                               "HERDR_PLUGIN_STATE_DIR": str(state_dir), "HERDR_SOCKET_PATH": "/nonexistent.sock"})
        self.assertEqual(rt.rows_for(UUID), rows)
        self.assertEqual(rt.summary_for(UUID).tokens, 37000)
        self.assertEqual(rt.statusline_windows, {UUID: 200000})
        self.assertEqual(rt.rows_for("5e0c1f2a-0000-4000-8000-000000000001"), [])


if __name__ == "__main__":
    unittest.main()
