import stat
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_parking import idle, transcript

NOW = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


def summary(last_activity):
    return transcript.EMPTY._replace(last_activity=last_activity)


class FirstSeenTest(unittest.TestCase):
    def test_a_new_row_starts_at_its_last_conversation_line(self):
        last = NOW - timedelta(hours=3, minutes=5)
        tracker = idle.Tracker(Clock(), summary_for=lambda pane_id: summary(last))
        entry = tracker.poll("w1:p1", seq=18, status="idle")
        self.assertEqual((entry.since, entry.lower_bound), (last, False))

    def test_without_a_transcript_time_it_starts_now_as_a_lower_bound(self):
        for found in (None, transcript.EMPTY):
            with self.subTest(summary=found):
                tracker = idle.Tracker(Clock(), summary_for=lambda pane_id: found)
                entry = tracker.poll("w1:p1", seq=18, status="idle")
                self.assertEqual((entry.since, entry.lower_bound), (NOW, True))


class ChangeTest(unittest.TestCase):
    def test_a_new_state_change_seq_restarts_the_time_exactly(self):
        clock = Clock()
        tracker = idle.Tracker(clock, summary_for=lambda pane_id: None)
        tracker.poll("w1:p1", seq=18, status="idle")
        clock.advance(minutes=5)
        self.assertEqual(tracker.poll("w1:p1", seq=18, status="idle").since, NOW)
        clock.advance(minutes=5)
        entry = tracker.poll("w1:p1", seq=20, status="working")
        self.assertEqual((entry.since, entry.lower_bound, entry.status, entry.seq),
                         (NOW + timedelta(minutes=10), False, "working", 20))


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state" / "observed.json"

    def test_a_vanished_pane_is_dropped_at_the_next_save_and_the_rest_reloads(self):
        clock = Clock()
        tracker = idle.Tracker(clock, summary_for=lambda pane_id: None)
        tracker.poll("w1:p1", seq=18, status="idle")
        tracker.poll("w1:p2", seq=3, status="working")
        tracker.save(self.path, live_pane_ids={"w1:p1"})
        self.assertEqual(set(tracker.entries), {"w1:p1"})
        reloaded = idle.Tracker.load(self.path, clock, summary_for=lambda pane_id: None)
        self.assertEqual(reloaded.entries, tracker.entries)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)


class TextTest(unittest.TestCase):
    def test_idle_time_text_with_a_lower_bound_mark_and_none_while_working(self):
        entry = idle.Entry
        cases = [
            (entry(1, "idle", NOW - timedelta(minutes=12), False), "12m"),
            (entry(1, "done", NOW - timedelta(hours=3, minutes=5), False), "3h05m"),
            (entry(1, "idle", NOW - timedelta(days=2, hours=1), True), "≥2d"),
            (entry(1, "blocked", NOW - timedelta(minutes=12), False), "12m"),
            (entry(1, "working", NOW - timedelta(minutes=12), False), "—"),
        ]
        for given, text in cases:
            with self.subTest(entry=given):
                self.assertEqual(idle.text(given, NOW), text)
        self.assertEqual(idle.text(None, NOW), "")


class BrokenFileTest(SaveTest):
    def test_a_missing_or_broken_file_starts_empty(self):
        clock = Clock()
        self.assertEqual(idle.Tracker.load(self.path, clock, summary_for=lambda p: None).entries, {})
        self.path.parent.mkdir(parents=True)
        for text in ("{broken", "[]", '{"w1:p1": {"seq": 1}}', '{"w1:p1": 5}',
                     '{"w1:p1": {"seq": 1, "status": "idle", "since": "later", "lower_bound": false}}'):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                self.assertEqual(idle.Tracker.load(self.path, clock, summary_for=lambda p: None).entries, {})

    def test_the_save_is_atomic(self):
        tracker = idle.Tracker(Clock(), summary_for=lambda p: None)
        tracker.poll("w1:p1", seq=1, status="idle")
        tracker.save(self.path, live_pane_ids={"w1:p1"})
        before = self.path.read_text(encoding="utf-8")
        tracker.poll("w1:p2", seq=1, status="idle")
        with unittest.mock.patch.object(idle.storage.json, "dump", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                tracker.save(self.path, live_pane_ids={"w1:p1", "w1:p2"})
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
