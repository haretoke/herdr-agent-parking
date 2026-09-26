import tempfile
import unittest
from pathlib import Path

from agent_parking import config


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "config.json"
        self.logged = []

    def load(self):
        return config.load(self.path, self.logged.append)

    def write(self, text):
        self.path.write_text(text, encoding="utf-8")

    def test_a_missing_file_gives_the_defaults_without_a_log_line(self):
        self.assertEqual(self.load(), config.DEFAULTS)
        self.assertEqual(self.logged, [])

    def test_the_defaults_are_the_documented_ones(self):
        self.assertEqual(config.DEFAULTS, {
            "poll_seconds": 2,
            "exit_timeout_seconds": 20,
            "start_timeout_ms": 30000,
            "on_park": "keep",
            "parked_label_format": "💤 {title}",
            "send_note_as_prompt": False,
            "bulk_idle_minutes": 60,
            "claude_command": "claude",
            "resumed_keep_days": 30,
            "records_dir": None,
            "claude_config_dir": None,
            "context_window_by_model": {},
            "prepare_command": "/prepare-compact",
            "prepare_prompt": None,
            "prepare_timeout_seconds": 600,
            "compact_timeout_seconds": 300,
        })

    def test_an_unusable_file_gives_the_defaults_and_a_reason(self):
        cases = [
            ("", "empty"),
            ("   \n", "empty"),
            ("{not json", "not valid JSON"),
            ("[1, 2]", "not a JSON object"),
            ("\"text\"", "not a JSON object"),
        ]
        for text, reason in cases:
            with self.subTest(text=text):
                self.logged.clear()
                self.write(text)
                self.assertEqual(self.load(), config.DEFAULTS)
                self.assertEqual(len(self.logged), 1)
                self.assertIn(reason, self.logged[0])

    def test_a_mistyped_value_falls_back_to_its_default_and_keeps_the_others(self):
        self.write('{"poll_seconds": "fast", "on_park": "drop", "send_note_as_prompt": 1,'
                   ' "exit_timeout_seconds": true, "bulk_idle_minutes": 30}')
        loaded = self.load()
        self.assertEqual(loaded["poll_seconds"], 2)
        self.assertEqual(loaded["on_park"], "keep")
        self.assertEqual(loaded["send_note_as_prompt"], False)
        self.assertEqual(loaded["exit_timeout_seconds"], 20)
        self.assertEqual(loaded["bulk_idle_minutes"], 30)
        for key in ("poll_seconds", "on_park", "send_note_as_prompt", "exit_timeout_seconds"):
            self.assertTrue(any(key in line for line in self.logged), key)
        self.assertFalse(any("bulk_idle_minutes" in line for line in self.logged))

    def test_an_unknown_key_is_ignored_with_a_reason(self):
        self.write('{"poll_second": 5}')
        self.assertEqual(self.load(), config.DEFAULTS)
        self.assertEqual(len(self.logged), 1)
        self.assertIn("poll_second", self.logged[0])

    def test_valid_values_are_used(self):
        self.write('{"poll_seconds": 0.5, "on_park": "close", "parked_label_format": "[parked] {title}",'
                   ' "send_note_as_prompt": true, "prepare_prompt": "Prepare to compact."}')
        loaded = self.load()
        self.assertEqual(loaded["poll_seconds"], 0.5)
        self.assertEqual(loaded["on_park"], "close")
        self.assertEqual(loaded["parked_label_format"], "[parked] {title}")
        self.assertIs(loaded["send_note_as_prompt"], True)
        self.assertEqual(loaded["prepare_prompt"], "Prepare to compact.")
        self.assertEqual(self.logged, [])

    def test_context_window_by_model_keeps_only_prefixes_with_positive_integers(self):
        self.write('{"context_window_by_model": {"claude-haiku": 200000, "claude-opus-5": 1000000,'
                   ' "": 5, "claude-x": 0, "claude-y": "big", "claude-z": 1.5, "claude-w": true}}')
        loaded = self.load()
        self.assertEqual(loaded["context_window_by_model"], {"claude-haiku": 200000, "claude-opus-5": 1000000})
        for bad in ("''", "claude-x", "claude-y", "claude-z", "claude-w"):
            self.assertTrue(any(bad in line for line in self.logged), bad)

    def test_context_window_by_model_that_is_not_an_object_is_ignored(self):
        self.write('{"context_window_by_model": [200000]}')
        self.assertEqual(self.load()["context_window_by_model"], {})
        self.assertEqual(len(self.logged), 1)

    def test_the_preparation_sends_the_skill_and_falls_back_to_the_built_in_text(self):
        prep = config.preparation(self.load())
        self.assertEqual(prep.first, "/prepare-compact")
        self.assertEqual(prep.fallback, config.BUILT_IN_PREPARE_PROMPT)
        self.assertIn("<compact-focus>", config.BUILT_IN_PREPARE_PROMPT)

    def test_a_set_prepare_prompt_takes_precedence_and_has_no_fallback(self):
        self.write('{"prepare_command": "/my-prep", "prepare_prompt": "Save state, then give a focus."}')
        prep = config.preparation(self.load())
        self.assertEqual(prep.first, "Save state, then give a focus.")
        self.assertIsNone(prep.fallback)

    def test_a_custom_prepare_command_keeps_the_built_in_fallback(self):
        self.write('{"prepare_command": "/my-prep", "prepare_timeout_seconds": 900}')
        loaded = self.load()
        prep = config.preparation(loaded)
        self.assertEqual(prep.first, "/my-prep")
        self.assertEqual(prep.fallback, config.BUILT_IN_PREPARE_PROMPT)
        self.assertEqual(loaded["prepare_timeout_seconds"], 900)

    def test_the_defaults_are_not_shared_between_loads(self):
        first = self.load()
        first["context_window_by_model"]["claude-x"] = 1
        self.assertEqual(self.load()["context_window_by_model"], {})


if __name__ == "__main__":
    unittest.main()
