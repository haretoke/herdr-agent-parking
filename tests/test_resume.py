import unittest
from pathlib import Path

from agent_parking import records, resume
from tests.flows import SHELL, SHELL_PROCESS, UUID, FlowTestCase, pane_reply

PARKED = {"schema_version": 1, "session_id": UUID, "status": "parked", "pane_id": "w1:p2",
          "pane_id_history": [], "tab_id": "w1:t1", "workspace_id": "w1", "title": "work", "cwd": "/repo",
          "argv": ["/home/u/.local/bin/claude", "--model", "haiku", "--resume", "work"],
          "label_before": "api", "note": None, "parked_mode": "keep", "layout_hint": None}
STARTED = {"type": "agent_info", "agent": {"pane_id": "w1:p2", "agent_status": "idle"}}


class ResumeTestCase(FlowTestCase):
    def setUp(self):
        super().setUp()
        self.records_dir = Path(self.environ["HERDR_PLUGIN_STATE_DIR"]) / "records"

    def park_record(self, **fields):
        records.write(self.records_dir, dict(PARKED, **fields))

    def resuming(self, **overrides):
        script = {"pane.list": {"type": "pane_list", "panes": [SHELL["pane"]]},
                  "pane.get": [SHELL, pane_reply()], "pane.process_info": SHELL_PROCESS,
                  "agent.start": STARTED, "pane.rename": {"type": "pane_info"},
                  "pane.send_input": {"type": "ok"}}
        script.update(overrides)
        return self.flow(**script)


class StartTest(ResumeTestCase):
    def test_the_session_starts_in_its_pane_with_the_replayed_flags(self):
        self.park_record()
        resume.resume(self.resuming(), UUID)
        [start] = [r for r in self.fake.requests if r["method"] == "agent.start"]
        self.assertEqual(start["params"], {"name": "parking-2716af66", "kind": "claude", "pane_id": "w1:p2",
                                           "args": ["--resume", UUID, "--model", "haiku"],
                                           "timeout_ms": 30000})


if __name__ == "__main__":
    unittest.main()
