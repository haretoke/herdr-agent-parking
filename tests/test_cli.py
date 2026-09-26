import io
import json
import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from agent_parking import cli, state
from tests.fake_herdr import Error, FakeHerdr


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


class OpenTest(CliTestCase):
    def herdr(self, reply):
        fake = FakeHerdr({"plugin.pane.open": reply})
        self.addCleanup(fake.close)
        return fake

    def environ(self, fake, **extra):
        return dict({"HOME": str(self.home), "HERDR_SOCKET_PATH": fake.path, "HERDR_PLUGIN_ID": state.PLUGIN_ID,
                     "HERDR_PLUGIN_STATE_DIR": str(self.home / "state")}, **extra)

    def test_open_asks_herdr_for_the_dashboard_as_an_overlay_and_open_tab_as_a_tab(self):
        opened = {"type": "plugin_pane_opened", "plugin_pane": {"pane_id": "w3:p9"}}
        fake = self.herdr(opened)
        self.assertEqual(cli.main(["open"], self.environ(fake)), 0)
        self.assertEqual(cli.main(["open-tab"], self.environ(fake, HERDR_WORKSPACE_ID="w3")), 0)
        self.assertEqual([r["params"] for r in fake.requests], [
            {"plugin_id": state.PLUGIN_ID, "entrypoint": "dashboard", "placement": "overlay", "focus": True},
            {"plugin_id": state.PLUGIN_ID, "entrypoint": "dashboard", "placement": "tab", "focus": True,
             "workspace_id": "w3"}])

    def test_a_refused_open_exits_1_with_herdrs_reason(self):
        fake = self.herdr(Error("plugin_disabled", "plugin haretoke.agent-parking is disabled"))
        with unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(cli.main(["open"], self.environ(fake)), 1)
        self.assertIn("is disabled", stderr.getvalue())


class ListTest(CliTestCase):
    def test_list_prints_every_row_as_json_with_claudes_own_memory(self):
        pane = {"pane_id": "w1:p2", "tab_id": "w1:t1", "workspace_id": "w1", "agent": "claude", "agent_status": "idle",
                "cwd": "/repo", "terminal_title_stripped": "work",
                "agent_session": {"agent": "claude", "kind": "id", "value": UUID}}
        process = {"shell_pid": 100, "foreground_process_group_id": os.getpid(),
                   "foreground_processes": [{"pid": os.getpid(), "name": "python"}]}
        fake = FakeHerdr({"pane.list": {"type": "pane_list", "panes": [pane]},
                          "agent.list": {"type": "agent_list", "agents": []},
                          "workspace.list": {"type": "workspace_list", "workspaces": []},
                          "tab.list": {"type": "tab_list", "tabs": []},
                          "pane.process_info": {"type": "process_info", "process_info": process}})
        self.addCleanup(fake.close)
        environ = {"HOME": str(self.home), "HERDR_SOCKET_PATH": fake.path, "HERDR_PANE_ID": "w1:p2", "PATH": "/usr/bin:/bin"}
        with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(cli.main(["list"], environ), 0)
        [row] = json.loads(stdout.getvalue())
        self.assertEqual((row["pane_id"], row["session_id"], row["status"]), ("w1:p2", UUID, "idle"))
        self.assertGreater(row["claude_rss_kb"], 0)
        self.assertEqual(row["claude_rss_kb"], row["rss_kb"])


if __name__ == "__main__":
    unittest.main()
