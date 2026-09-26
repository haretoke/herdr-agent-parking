import unittest

from agent_parking import compact, records, resume
from tests.flows import SHELL, SHELL_PROCESS, UUID, FlowTestCase, pane_reply


class Spy:
    """Wraps a Herdr and records the socket timeout of every call."""

    def __init__(self, herdr):
        self.herdr = herdr
        self.timeouts = {}

    def call(self, method, params, timeout=None):
        self.timeouts.setdefault(method, []).append(timeout)
        return self.herdr.call(method, params, timeout=timeout)

    def __getattr__(self, name):
        method = getattr(type(self.herdr), name)
        return lambda *args, **kwargs: method(self, *args, **kwargs)


def boundary():
    return {"type": "system", "subtype": "compact_boundary", "timestamp": "2026-09-27T12:00:05Z"}


class WaitTimeoutTest(FlowTestCase):
    def spied(self, rt):
        rt.herdr = Spy(rt.herdr)
        return rt.herdr

    def test_the_preparation_and_compact_outlast_their_herdr_side_waits(self):
        self.settings.update(prepare_timeout_seconds=600, compact_timeout_seconds=300)
        rt = self.flow(**{"pane.get": pane_reply()})
        spy = self.spied(rt)
        rt.rows_for = lambda session_id: [boundary()]
        compact.prepare(rt, "w1:p2")
        compact.run(rt, "w1:p2", "keep")
        prepare_timeout, compact_timeout = spy.timeouts["agent.prompt"]
        self.assertGreater(prepare_timeout, 600)
        self.assertGreater(compact_timeout, 300)

    def test_agent_start_outlasts_its_startup_timeout(self):
        records.write(self.flow().paths.records, {
            "schema_version": 1, "session_id": UUID, "status": "parked", "pane_id": "w1:p2",
            "pane_id_history": [], "cwd": "/repo", "argv": ["claude"], "label_before": None})
        rt = self.flow(**{"pane.list": {"type": "pane_list", "panes": [SHELL["pane"]]},
                          "pane.get": [SHELL, pane_reply()], "pane.process_info": SHELL_PROCESS,
                          "agent.start": {"type": "agent_info"}})
        spy = self.spied(rt)
        resume.resume(rt, UUID)
        [start_timeout] = spy.timeouts["agent.start"]
        self.assertGreater(start_timeout, self.settings["start_timeout_ms"] / 1000)


if __name__ == "__main__":
    unittest.main()
