import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent_parking import transcript

UUID = "2716af66-e4d8-4950-8185-97da891f78a9"


class TranscriptTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / ".claude"

    def put(self, project, name=UUID + ".jsonl", text=""):
        path = self.config / "projects" / project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class FindTest(TranscriptTestCase):
    def test_the_transcript_is_found_in_any_project_directory(self):
        path = self.put("-Users-u-work")
        self.put("-Users-u-other", name="0939a1b4-2ecb-4bd4-a241-59bd6732651f.jsonl")
        self.assertEqual(transcript.find(self.config, UUID), path)

    def test_none_or_several_give_no_result(self):
        self.assertIsNone(transcript.find(self.config, UUID))
        self.put("-a")
        self.put("-b")
        self.assertIsNone(transcript.find(self.config, UUID))

    def test_a_session_id_that_is_not_a_uuid_is_not_globbed(self):
        self.put("-a", name="x.jsonl")
        for bad in ("*", "x", "../x", ""):
            with self.subTest(session_id=bad):
                self.assertIsNone(transcript.find(self.config, bad))


def jsonl(*rows):
    return "".join(json.dumps(row) + "\n" for row in rows)


class TailTest(TranscriptTestCase):
    def test_a_file_under_the_cap_is_read_whole(self):
        rows = [{"n": i} for i in range(5)]
        path = self.put("-a", text=jsonl(*rows))
        self.assertEqual(transcript.read_tail(path, 10_000), rows)

    def test_a_line_cut_by_the_cap_is_dropped_and_the_rest_kept(self):
        rows = [{"n": i, "pad": "x" * 50} for i in range(40)]
        text = jsonl(*rows)
        path = self.put("-a", text=text)
        cap = 200
        got = transcript.read_tail(path, cap)
        tail = text.encode()[-cap:]
        expected_count = tail.count(b"\n") - (0 if text.encode()[-cap - 1:-cap] == b"\n" else 1)
        self.assertEqual(got, rows[-expected_count:])
        self.assertTrue(all(len(json.dumps(r)) + 1 <= cap for r in got))

    def test_a_cap_that_falls_on_a_line_start_keeps_that_line(self):
        rows = [{"n": 1}, {"n": 2}, {"n": 3}]
        text = jsonl(*rows)
        path = self.put("-a", text=text)
        cap = len(jsonl(rows[1], rows[2]))
        self.assertEqual(transcript.read_tail(path, cap), rows[1:])

    def test_a_huge_file_is_read_only_at_its_end(self):
        path = self.put("-a", text=jsonl(*[{"n": i, "pad": "y" * 500} for i in range(10_000)]))
        got = transcript.read_tail(path, 2_000)
        self.assertEqual([r["n"] for r in got], list(range(10_000 - len(got), 10_000)))
        self.assertLessEqual(len(got), 4)

    def test_lines_that_are_not_json_objects_are_skipped(self):
        path = self.put("-a", text='{"n": 1}\nnot json\n[1]\n{"n": 2}\n')
        self.assertEqual(transcript.read_tail(path, 10_000), [{"n": 1}, {"n": 2}])


class CacheTest(TranscriptTestCase):
    def test_a_result_is_reused_until_the_mtime_or_the_size_changes(self):
        path = self.put("-a", text='{"n": 1}\n')
        reads = []

        def read(p):
            reads.append(p)
            return len(reads)

        cache = transcript.Cache(read)
        self.assertEqual(cache.get(path), 1)
        self.assertEqual(cache.get(path), 1)
        with open(path, "a", encoding="utf-8") as f:
            f.write('{"n": 2}\n')
        self.assertEqual(cache.get(path), 2)
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        self.assertEqual(cache.get(path), 3)
        self.assertEqual(len(reads), 3)

    def test_a_missing_file_is_none_and_not_cached(self):
        cache = transcript.Cache(lambda p: "read")
        missing = self.config / "projects" / "-a" / "gone.jsonl"
        self.assertIsNone(cache.get(missing))
        self.assertIsNone(cache.get(None))


def assistant(inp=0, create=0, read=0, out=0, model="claude-haiku-4-5-20251001", ts="2026-09-26T16:39:00Z"):
    return {"type": "assistant", "timestamp": ts, "message": {"model": model, "usage": {
        "input_tokens": inp, "cache_creation_input_tokens": create,
        "cache_read_input_tokens": read, "output_tokens": out}}}


def user(text="hi", ts="2026-09-26T16:38:00Z", **flags):
    row = {"type": "user", "timestamp": ts, "message": {"role": "user", "content": text}}
    row.update(flags)
    return row


def boundary(ts="2026-09-26T16:39:48Z"):
    return {"type": "system", "subtype": "compact_boundary", "timestamp": ts,
            "compactMetadata": {"trigger": "manual", "preTokens": 36956, "postTokens": 4257}}


class ContextTokensTest(unittest.TestCase):
    def test_the_tokens_are_the_three_input_counts_of_the_last_assistant_usage(self):
        rows = [user(), assistant(10, 7555, 29325, out=65), user("again"),
                assistant(1, 2, 3, out=999, model="claude-opus-5-5"), {"type": "cost-state"}]
        summary = transcript.summarize(rows)
        self.assertEqual(summary.tokens, 6)
        self.assertEqual(summary.model, "claude-opus-5-5")

    def test_usage_before_the_last_boundary_does_not_count(self):
        rows = [assistant(10, 7555, 29325), boundary(), user("summary", isCompactSummary=True)]
        self.assertIsNone(transcript.summarize(rows).tokens)
        rows.append(assistant(4000, 200, 0))
        self.assertEqual(transcript.summarize(rows).tokens, 4200)

    def test_rows_without_usage_give_no_tokens(self):
        self.assertIsNone(transcript.summarize([user(), {"type": "assistant", "message": {}}]).tokens)
        self.assertIsNone(transcript.summarize([]).tokens)


class CompactedTest(unittest.TestCase):
    def test_compacted_is_a_last_boundary_without_assistant_usage_after_it(self):
        after_boundary = [user("summary", isCompactSummary=True), user("caveat", isMeta=True),
                          user("<command-name>/compact</command-name>"), {"type": "attachment"},
                          {"type": "system", "subtype": "informational"}]
        rows = [user(), assistant(10, 20, 30), boundary()] + after_boundary
        self.assertTrue(transcript.summarize(rows).compacted)
        self.assertFalse(transcript.summarize(rows + [assistant(5)]).compacted)
        self.assertFalse(transcript.summarize([user(), assistant(1)]).compacted)
        self.assertFalse(transcript.summarize([]).compacted)

    def test_the_compacted_time_is_the_boundary_timestamp(self):
        rows = [boundary("2026-09-26T16:00:00Z"), assistant(1), boundary("2026-09-26T16:39:48Z"),
                user("summary", ts="2026-09-26T16:39:48Z", isCompactSummary=True)]
        summary = transcript.summarize(rows)
        self.assertEqual(summary.compacted_at, datetime(2026, 9, 26, 16, 39, 48, tzinfo=timezone.utc))
        self.assertIsNone(transcript.summarize(rows + [assistant(2)]).compacted_at)


class WindowTest(TranscriptTestCase):
    def test_the_setting_by_longest_model_prefix_then_the_statusline_file_then_unknown(self):
        by_model = {"claude-haiku": 200_000, "claude-opus": 200_000, "claude-opus-5": 1_000_000}
        from_statusline = {UUID: 1_000_000}
        cases = [
            ("claude-haiku-4-5-20251001", UUID, 200_000),
            ("claude-opus-5-5", UUID, 1_000_000),
            ("claude-opus-4-1", UUID, 200_000),
            ("claude-sonnet-5", UUID, 1_000_000),
            ("claude-sonnet-5", "0939a1b4-2ecb-4bd4-a241-59bd6732651f", None),
            (None, UUID, 1_000_000),
        ]
        for model, session_id, expected in cases:
            with self.subTest(model=model, session_id=session_id):
                self.assertEqual(transcript.window_size(model, session_id, by_model, from_statusline), expected)

    def test_the_statusline_file_maps_session_ids_to_positive_sizes(self):
        path = self.config / "context-windows.json"
        self.assertEqual(transcript.statusline_windows(path), {})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({UUID: 200000, "x": 5, "0939a1b4-2ecb-4bd4-a241-59bd6732651f": "big"}),
                        encoding="utf-8")
        self.assertEqual(transcript.statusline_windows(path), {UUID: 200000})
        path.write_text("{broken", encoding="utf-8")
        self.assertEqual(transcript.statusline_windows(path), {})


class LoadTest(TranscriptTestCase):
    def test_a_missing_unreadable_or_empty_transcript_gives_an_empty_summary(self):
        empty = transcript.load(self.put("-a", text=""))
        self.assertEqual(empty, transcript.EMPTY)
        self.assertEqual((empty.tokens, empty.compacted), (None, False))
        self.assertEqual(transcript.load(self.config / "projects" / "-a" / "missing.jsonl"), transcript.EMPTY)
        self.assertEqual(transcript.load(self.put("-b", text="garbage\n")), transcript.EMPTY)
        directory = self.config / "projects" / "-c" / (UUID + ".jsonl")
        directory.mkdir(parents=True)
        self.assertEqual(transcript.load(directory), transcript.EMPTY)

    def test_a_readable_transcript_is_summarized_from_its_tail(self):
        path = self.put("-a", text=jsonl(user(), assistant(10, 7555, 29325)))
        self.assertEqual(transcript.load(path).tokens, 36890)


class PercentTest(unittest.TestCase):
    def test_the_percentage_is_truncated_like_the_statusline(self):
        for tokens, window, expected in [(36890, 200_000, 18), (199_999, 200_000, 99), (0, 200_000, 0),
                                         (279_596, 1_000_000, 27), (250_000, 200_000, 125)]:
            with self.subTest(tokens=tokens, window=window):
                self.assertEqual(transcript.percent(tokens, window), expected)

    def test_no_percentage_without_a_window_or_tokens(self):
        self.assertIsNone(transcript.percent(36890, None))
        self.assertIsNone(transcript.percent(None, 200_000))


if __name__ == "__main__":
    unittest.main()
