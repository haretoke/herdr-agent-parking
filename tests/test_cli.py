import io
import json
import os
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from agent_parking import cli, compact, park, presence, recreate, resume, state, transcript
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
        self.assertTrue(rt.has_transcript(UUID))
        self.assertFalse(rt.has_transcript("5e0c1f2a-0000-4000-8000-000000000001"))


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
            {"plugin_id": state.PLUGIN_ID, "entrypoint": "dashboard", "placement": "overlay", "focus": True,
             "env": {"AGENT_PARKING_PLACEMENT": "overlay"}},
            {"plugin_id": state.PLUGIN_ID, "entrypoint": "dashboard", "placement": "tab", "focus": True,
             "env": {"AGENT_PARKING_PLACEMENT": "tab"}, "workspace_id": "w3"}])

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


class ShellCommandTestCase(CliTestCase):
    def run_cli(self, args, **extra):
        environ = dict({"HOME": str(self.home), "HERDR_SOCKET_PATH": "/nonexistent.sock"}, **extra)
        with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as out, \
                unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            code = cli.main(args, environ)
        return code, out.getvalue(), err.getvalue()


class ParkCommandTest(ShellCommandTestCase):
    def test_park_runs_the_park_flow_with_the_note_and_exits_1_when_it_does_not_park(self):
        with unittest.mock.patch.object(park, "park", return_value=park.Outcome("parked", "", {})) as flow:
            code, out, _ = self.run_cli(["park", "w1:p2", "--note", "wiki"])
        self.assertEqual((code, out.strip()), (0, "parked w1:p2"))
        self.assertEqual(flow.call_args[0][1:], ("w1:p2", "wiki"))
        with unittest.mock.patch.object(park, "park", return_value=park.Outcome("refused", "Claude is working", None)):
            code, _, err = self.run_cli(["park", "w1:p2"])
        self.assertEqual(code, 1)
        self.assertIn("refused w1:p2: Claude is working", err)

    def test_outside_herdr_the_command_says_so(self):
        code, _, err = self.run_cli(["park", "w1:p2"], HERDR_SOCKET_PATH="")
        self.assertEqual(code, 1)
        self.assertIn("not running inside Herdr", err)


class ResumeCommandTest(ShellCommandTestCase):
    def test_resume_runs_the_resume_flow_and_a_gone_workspace_needs_the_flag(self):
        record = {"pane_id": "w1:p2"}
        with unittest.mock.patch.object(resume, "resume", return_value=resume.Outcome("resumed", "", record)) as flow:
            code, out, _ = self.run_cli(["resume", UUID])
        self.assertEqual((code, out.strip()), (0, "resumed " + UUID))
        self.assertEqual(flow.call_args[0][1:], (UUID,))
        self.assertEqual(flow.call_args[1], {"new_workspace": False})
        refused = resume.Outcome("refused", recreate.NEEDS_WORKSPACE, record)
        with unittest.mock.patch.object(resume, "resume", return_value=refused) as flow:
            code, _, err = self.run_cli(["resume", UUID])
            self.assertIn("--new-workspace", err)
            self.assertEqual(code, 1)
            self.run_cli(["resume", UUID, "--new-workspace"])
        self.assertEqual(flow.call_args[1], {"new_workspace": True})


REPLY = transcript.Reply(found=True, text="Saved the port map.\n<compact-focus>port map</compact-focus>",
                         focus="port map")


class CompactCommandTest(ShellCommandTestCase):
    def patched(self, prepared):
        prepare = unittest.mock.patch.object(compact, "prepare", return_value=prepared)
        run = unittest.mock.patch.object(compact, "run", return_value=compact.Outcome("compacted", "", None))
        return prepare, run

    def test_compact_prepares_prints_the_report_and_compacts_with_the_proposed_or_given_focus(self):
        prepare, run = self.patched(compact.Outcome("prepared", "", REPLY))
        with prepare, run as flow:
            code, out, _ = self.run_cli(["compact", "w1:p2"])
            self.assertEqual(flow.call_args[0][1:], ("w1:p2", "port map"))
            self.run_cli(["compact", "w1:p2", "--focus", "the TODO list"])
            self.assertEqual(flow.call_args[0][1:], ("w1:p2", "the TODO list"))
        self.assertEqual(code, 0)
        self.assertIn("Saved the port map.", out)
        self.assertIn("focus: port map", out)
        self.assertNotIn("Enter to compact", out)
        self.assertTrue(out.strip().endswith("compacted w1:p2"))

    def test_a_preparation_that_stops_compacts_nothing_and_exits_1(self):
        prepare, run = self.patched(compact.Outcome("blocked", "Claude stopped at a dialog", None))
        with prepare, run as flow:
            code, _, err = self.run_cli(["compact", "w1:p2"])
        self.assertEqual(code, 1)
        self.assertIn("blocked w1:p2: Claude stopped at a dialog", err)
        flow.assert_not_called()


OPENED = {"type": "plugin_pane_opened", "plugin_pane": {"pane_id": "w3:p9"}}
DASHBOARD_PANE = {"type": "pane_info", "pane": {"pane_id": "w1:p8", "tab_id": "w1:t1", "workspace_id": "w1"}}


class SingleDashboardTest(CliTestCase):
    """Seen on the Mac: each open added a dashboard, and the earlier ones stayed."""

    def environ(self, fake):
        return {"HOME": str(self.home), "HERDR_SOCKET_PATH": fake.path, "HERDR_PLUGIN_ID": state.PLUGIN_ID,
                "HERDR_PLUGIN_STATE_DIR": str(self.home / "state")}

    def herdr(self, **script):
        fake = FakeHerdr(dict({"plugin.pane.open": OPENED, "plugin.pane.close": {"type": "ok"},
                               "plugin.pane.focus": {"type": "ok"}, "pane.get": DASHBOARD_PANE}, **script))
        self.addCleanup(fake.close)
        return fake

    def announce(self, placement, pid=None):
        presence.announce(self.home / "state" / "dashboard.json", "w1:p8", pid or os.getpid(), placement)

    def calls(self, fake):
        return [(r["method"], r["params"].get("pane_id")) for r in fake.requests if r["method"] != "pane.get"]

    def test_an_open_overlay_dashboard_is_closed_and_opened_again_where_open_is_used(self):
        fake = self.herdr()
        self.announce("overlay")
        self.assertEqual(cli.main(["open"], self.environ(fake)), 0)
        self.assertEqual(self.calls(fake), [("plugin.pane.close", "w1:p8"), ("plugin.pane.open", None)])

    def test_a_dashboard_kept_in_a_tab_is_focused_by_either_action(self):
        for action in ("open", "open-tab"):
            with self.subTest(action=action):
                fake = self.herdr()
                self.announce("tab")
                self.assertEqual(cli.main([action], self.environ(fake)), 0)
                self.assertEqual(self.calls(fake), [("plugin.pane.focus", "w1:p8")])

    def test_a_dashboard_whose_process_or_pane_is_gone_does_not_count(self):
        ended = subprocess.Popen(["true"])
        ended.wait()
        for pid, script in ((ended.pid, {}), (None, {"pane.get": Error("pane_not_found")})):
            with self.subTest(pid=pid):
                fake = self.herdr(**script)
                self.announce("overlay", pid=pid)
                self.assertEqual(cli.main(["open"], self.environ(fake)), 0)
                self.assertEqual(self.calls(fake), [("plugin.pane.open", None)])


if __name__ == "__main__":
    unittest.main()
