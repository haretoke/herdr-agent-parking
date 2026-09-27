"""Pieces the flow tests (park, compact, resume) share: fake Herdr replies and a Runtime."""

import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent_parking import config, herdr_api, runtime, state
from tests.fake_herdr import FakeHerdr
from tests.fakes import FakeSystem

UUID = "2716af66-e4d8-4950-8185-97da891f78a9"
NOW = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)


def pane_reply(status="idle", agent="claude", session_id=UUID, label=None, pane_id="w1:p2"):
    pane = {"pane_id": pane_id, "tab_id": "w1:t1", "workspace_id": "w1", "agent": agent,
            "agent_status": status, "cwd": "/repo", "label": label, "terminal_title_stripped": "work"}
    if session_id:
        pane["agent_session"] = {"agent": "claude", "kind": "id", "value": session_id}
    return {"type": "pane_info", "pane": pane}


class FlowRuntimeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.environ = {"HOME": self.tmp.name, "HERDR_PLUGIN_ID": state.PLUGIN_ID,
                        "HERDR_PLUGIN_STATE_DIR": str(Path(self.tmp.name) / "state")}
        self.settings = copy.deepcopy(config.DEFAULTS)
        self.slept = []

    def runtime(self, script):
        self.fake = FakeHerdr(script)
        self.addCleanup(self.fake.close)
        return runtime.Runtime(herdr=herdr_api.Herdr(self.fake.path), system=None,
                               paths=state.paths(self.environ, self.settings), settings=self.settings,
                               clock=lambda: NOW, environ=self.environ, sleep=self.slept.append)


RULE = "─" * 40


def screen_reply(input_line):
    text = "\r\n".join(["⏺ OK", RULE, input_line, RULE, "  ctx 18%"])
    return {"type": "agent_read", "read": {"pane_id": "w1:p2", "workspace_id": "w1", "tab_id": "w1:t1",
                                           "source": "visible", "format": "ansi", "text": text,
                                           "revision": 1, "truncated": False}}


SHELL = pane_reply(status="unknown", agent=None, session_id=None)
PROCESS = {"type": "process_info", "process_info": {
    "shell_pid": 100, "foreground_process_group_id": 200,
    "foreground_processes": [{"pid": 200, "name": "2.1.283", "cwd": "/repo",
                              "argv": ["/home/u/.local/bin/claude", "--model", "haiku"]},
                             {"pid": 201, "name": "node"}]}}
SHELL_PROCESS = {"type": "process_info", "process_info": {
    "shell_pid": 100, "foreground_process_group_id": 100,
    "foreground_processes": [{"pid": 100, "name": "zsh"}]}}


def pane_list(*where):
    """A `pane.list` reply with a pane for each (pane_id, tab_id, workspace_id)."""
    return {"type": "pane_list", "panes": [{"pane_id": pane_id, "tab_id": tab_id, "workspace_id": workspace_id}
                                           for pane_id, tab_id, workspace_id in where]}


# The Claude pane `w1:p2` beside a shell `w1:p1` in one tab.
BESIDE_A_SHELL = pane_list(("w1:p1", "w1:t1", "w1"), ("w1:p2", "w1:t1", "w1"))
ALONE = pane_list(("w1:p2", "w1:t1", "w1"))


class FlowTestCase(FlowRuntimeTestCase):
    def flow(self, **overrides):
        script = {"pane.get": [pane_reply(), SHELL], "agent.read": screen_reply("❯"), "pane.send_keys": {"type": "ok"},
                  "pane.process_info": [PROCESS, SHELL_PROCESS], "agent.prompt": {"type": "ok"},
                  "pane.rename": {"type": "pane_info"}, "pane.close": {"type": "ok"},
                  "pane.list": BESIDE_A_SHELL}
        script.update(overrides)
        rt = self.runtime(script)
        rt.system = FakeSystem(proc=False)
        return rt

    def saved(self):
        path = Path(self.environ["HERDR_PLUGIN_STATE_DIR"]) / "records" / (UUID + ".json")
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
