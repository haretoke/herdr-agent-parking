import unittest

from agent_parking import compact, config
from tests.fake_herdr import Error
from tests.flows import SHELL, FlowTestCase, pane_reply, screen_reply


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
        self.assertEqual(prompt["params"]["wait"], {"until": ["idle", "done", "blocked"], "timeout_ms": 900_000})


def user(text):
    return {"type": "user", "timestamp": "2026-09-27T11:59:00Z", "message": {"content": text}}


def said(text):
    return {"type": "assistant", "timestamp": "2026-09-27T11:59:30Z",
            "message": {"content": [{"type": "text", "text": text}], "usage": {"input_tokens": 1}}}


SKILL_LINE = "<command-message>prepare-compact</command-message>\n<command-name>/prepare-compact</command-name>"


class FocusTest(FlowTestCase):
    def test_the_focus_is_read_from_the_reply_to_the_preparation(self):
        rt = self.flow()
        reply = [user(SKILL_LINE), said("Saved.\n<compact-focus>keep the plan</compact-focus>")]
        rt.rows_for = lambda session_id: reply if "agent.prompt" in self.fake.methods() else []
        outcome = compact.prepare(rt, "w1:p2")
        self.assertIn("agent.prompt", self.fake.methods())
        self.assertEqual((outcome.kind, outcome.reply.focus), ("prepared", "keep the plan"))
        self.assertIn("Saved.", outcome.reply.text)


def boundary(ts):
    return {"type": "system", "subtype": "compact_boundary", "timestamp": ts,
            "compactMetadata": {"trigger": "manual"}}


class RunTest(FlowTestCase):
    def test_the_focus_goes_out_as_one_line_and_an_empty_one_as_compact_alone(self):
        for focus, text in [("keep the plan\nand the ids", "/compact keep the plan and the ids"),
                            ("", "/compact"), ("  ", "/compact")]:
            with self.subTest(focus=focus):
                rt = self.flow()
                rt.rows_for = lambda session_id: [boundary("2026-09-27T12:00:05Z")]
                compact.run(rt, "w1:p2", focus)
                [prompt] = [r for r in self.fake.requests if r["method"] == "agent.prompt"]
                self.assertEqual(prompt["params"]["text"], text)
                self.assertEqual(prompt["params"]["wait"], {"until": ["idle", "done"], "timeout_ms": 300_000})

    def test_it_is_done_when_a_boundary_newer_than_the_request_is_there(self):
        rt = self.flow()
        rt.rows_for = lambda session_id: [boundary("2026-09-27T11:00:00Z"), boundary("2026-09-27T12:00:05Z")]
        self.assertEqual(compact.run(rt, "w1:p2", "keep").kind, "compacted")

    def test_no_new_boundary_is_compact_failed(self):
        rt = self.flow()
        rt.rows_for = lambda session_id: [boundary("2026-09-27T11:00:00Z")]
        outcome = compact.run(rt, "w1:p2", "keep")
        self.assertEqual(outcome.kind, "compact_failed")
        self.assertIn("300", outcome.message)


class BlockedTest(FlowTestCase):
    def test_a_preparation_stopped_at_a_dialog_ends_the_flow_there(self):
        blocked = {"type": "agent_prompted", "agent": {"pane_id": "w1:p2", "agent_status": "blocked"}}
        rt = self.flow(**{"agent.prompt": blocked})
        outcome = compact.prepare(rt, "w1:p2")
        self.assertEqual(outcome.kind, "blocked")
        self.assertIn("go to the pane", outcome.message)


class SkillMissingTest(FlowTestCase):
    def unknown_screen(self):
        reply = screen_reply("❯")
        reply["read"]["text"] = "⏺ Unknown command: /prepare-compact\r\n" + reply["read"]["text"]
        return reply

    def test_an_unknown_command_falls_back_to_the_built_in_text(self):
        stalled = Error("agent_prompt_stalled", "no working or blocked state within 5000 ms")
        rt = self.flow(**{"agent.prompt": [stalled, {"type": "agent_prompted"}],
                          "agent.read": [screen_reply("❯"), self.unknown_screen()]})
        outcome = compact.prepare(rt, "w1:p2")
        texts = [r["params"]["text"] for r in self.fake.requests if r["method"] == "agent.prompt"]
        self.assertEqual(texts, ["/prepare-compact", config.BUILT_IN_PREPARE_PROMPT])
        self.assertEqual(outcome.kind, "prepared")
        self.assertIn("built-in", outcome.message)

    def test_without_a_fallback_it_fails(self):
        self.settings["prepare_prompt"] = "/my-own-prep"
        stalled = Error("agent_prompt_stalled", "no working or blocked state within 5000 ms")
        rt = self.flow(**{"agent.prompt": stalled,
                          "agent.read": [screen_reply("❯"), self.unknown_screen()]})
        outcome = compact.prepare(rt, "w1:p2")
        self.assertEqual(outcome.kind, "prepare_failed")
        self.assertIn("Unknown command", outcome.message)


class AgainTest(FlowTestCase):
    def test_c_again_reuses_a_finished_preparation_without_sending_it_again(self):
        rt = self.flow()
        rt.rows_for = lambda session_id: [user(SKILL_LINE), said("<compact-focus>keep the plan</compact-focus>")]
        outcome = compact.prepare(rt, "w1:p2")
        self.assertNotIn("agent.prompt", self.fake.methods())
        self.assertEqual((outcome.kind, outcome.reply.focus), ("prepared", "keep the plan"))
        self.assertIn("earlier preparation", outcome.message)

    def test_a_preparation_already_followed_by_a_compaction_is_not_reused(self):
        rt = self.flow()
        rows = [user(SKILL_LINE), said("<compact-focus>old</compact-focus>"), boundary("2026-09-27T11:59:50Z")]
        rt.rows_for = lambda session_id: rows
        compact.prepare(rt, "w1:p2")
        self.assertIn("agent.prompt", self.fake.methods())

    def test_a_reply_without_a_tag_is_not_reused(self):
        rt = self.flow()
        rt.rows_for = lambda session_id: [user(SKILL_LINE), said("working on it")]
        compact.prepare(rt, "w1:p2")
        self.assertIn("agent.prompt", self.fake.methods())


class CompactThenParkTest(FlowTestCase):
    def test_a_compaction_is_followed_by_the_park_with_the_note(self):
        rt = self.flow(**{"pane.get": [pane_reply(), pane_reply(), SHELL]})
        rt.rows_for = lambda session_id: [boundary("2026-09-27T12:00:05Z")]
        compacted, parked = compact.compact_then_park(rt, "w1:p2", focus="keep", note="after lunch")
        self.assertEqual((compacted.kind, parked.kind), ("compacted", "parked"))
        texts = [r["params"]["text"] for r in self.fake.requests if r["method"] == "agent.prompt"]
        self.assertEqual(texts, ["/compact keep", "/exit"])
        self.assertEqual(self.saved()["note"], "after lunch")

    def test_a_failed_compaction_does_not_park(self):
        rt = self.flow()
        rt.rows_for = lambda session_id: []
        compacted, parked = compact.compact_then_park(rt, "w1:p2", focus="keep", note="x")
        self.assertEqual(compacted.kind, "compact_failed")
        self.assertIsNone(parked)
        texts = [r["params"]["text"] for r in self.fake.requests if r["method"] == "agent.prompt"]
        self.assertEqual(texts, ["/compact keep"])


class ConfirmationTest(unittest.TestCase):
    def test_the_box_shows_the_end_of_the_report_and_the_editable_focus(self):
        report = "\n".join(["line %d" % i for i in range(1, 11)] +
                           ["<compact-focus>keep the plan</compact-focus>", "`/compact keep the plan`"])
        reply = compact.transcript.Reply(found=True, text=report, focus="keep the plan")
        lines = compact.confirmation(reply)
        text = "\n".join(lines)
        self.assertIn("line 10", text)
        self.assertNotIn("line 1\n", text + "\n")
        self.assertNotIn("<compact-focus>", text)
        self.assertIn("focus: keep the plan", text)
        self.assertIn("e to edit", text)

    def test_an_empty_focus_is_shown_as_such(self):
        lines = compact.confirmation(compact.transcript.Reply(found=True, text="Nothing to save.", focus=""))
        self.assertIn("focus: (none, /compact alone)", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
