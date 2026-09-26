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


def user(text):
    return {"type": "user", "timestamp": "2026-09-27T11:59:00Z", "message": {"content": text}}


def said(text):
    return {"type": "assistant", "timestamp": "2026-09-27T11:59:30Z",
            "message": {"content": [{"type": "text", "text": text}], "usage": {"input_tokens": 1}}}


SKILL_LINE = "<command-message>prepare-compact</command-message>\n<command-name>/prepare-compact</command-name>"


class FocusTest(FlowTestCase):
    def test_the_focus_is_read_from_the_reply_to_the_preparation(self):
        rt = self.flow()
        rt.rows_for = lambda session_id: [user(SKILL_LINE), said("Saved.\n<compact-focus>keep the plan</compact-focus>")]
        outcome = compact.prepare(rt, "w1:p2")
        self.assertEqual((outcome.kind, outcome.reply.focus), ("prepared", "keep the plan"))
        self.assertIn("Saved.", outcome.reply.text)


if __name__ == "__main__":
    unittest.main()
