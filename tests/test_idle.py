import unittest
from datetime import datetime, timedelta, timezone

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


if __name__ == "__main__":
    unittest.main()
