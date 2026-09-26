import unittest

from agent_parking import compact
from tests.flows import FlowTestCase, pane_reply, screen_reply


class PrepareTest(FlowTestCase):
    def test_an_idle_or_done_claude_with_an_empty_box_gets_the_preparation_command(self):
        for status in ("idle", "done"):
            with self.subTest(status=status):
                rt = self.flow(**{"pane.get": pane_reply(status=status)})
                compact.prepare(rt, "w1:p2")
                [prompt] = [r for r in self.fake.requests if r["method"] == "agent.prompt"]
                self.assertEqual((prompt["params"]["target"], prompt["params"]["text"]),
                                 ("w1:p2", "/prepare-compact"))

    def test_other_states_and_a_draft_are_refused(self):
        for overrides in ({"pane.get": pane_reply(status="working")},
                          {"agent.read": screen_reply("❯ half typed")}):
            with self.subTest(overrides=overrides):
                outcome = compact.prepare(self.flow(**overrides), "w1:p2")
                self.assertEqual(outcome.kind, "refused")
                self.assertNotIn("agent.prompt", self.fake.methods())


class PreparePromptTest(FlowTestCase):
    def test_a_set_prepare_prompt_is_sent_instead(self):
        self.settings["prepare_prompt"] = "Save state, then give a focus."
        compact.prepare(self.flow(), "w1:p2")
        [prompt] = [r for r in self.fake.requests if r["method"] == "agent.prompt"]
        self.assertEqual(prompt["params"]["text"], "Save state, then give a focus.")


class WaitTest(FlowTestCase):
    def test_the_preparation_is_awaited_in_the_same_request(self):
        self.settings["prepare_timeout_seconds"] = 900
        compact.prepare(self.flow(), "w1:p2")
        [prompt] = [r for r in self.fake.requests if r["method"] == "agent.prompt"]
        self.assertEqual(prompt["params"]["wait"], {"until": ["idle", "done"], "timeout_ms": 900_000})


if __name__ == "__main__":
    unittest.main()
