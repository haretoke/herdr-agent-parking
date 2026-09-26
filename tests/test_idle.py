import json
import stat
import subprocess
import sys
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
        tracker = idle.Tracker(Clock())
        entry = tracker.poll("w1:p1", seq=18, status="idle", summary=summary(last))
        self.assertEqual((entry.since, entry.lower_bound), (last, False))

    def test_without_a_transcript_time_it_starts_now_as_a_lower_bound(self):
        for found in (None, transcript.EMPTY):
            with self.subTest(summary=found):
                tracker = idle.Tracker(Clock())
                entry = tracker.poll("w1:p1", seq=18, status="idle", summary=found)
                self.assertEqual((entry.since, entry.lower_bound), (NOW, True))


class ChangeTest(unittest.TestCase):
    def test_a_new_state_change_seq_restarts_the_time_exactly(self):
        clock = Clock()
        tracker = idle.Tracker(clock)
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
        tracker = idle.Tracker(clock)
        tracker.poll("w1:p1", seq=18, status="idle")
        tracker.poll("w1:p2", seq=3, status="working")
        tracker.save(self.path, live_pane_ids={"w1:p1"})
        self.assertEqual(set(tracker.entries), {"w1:p1"})
        reloaded = idle.Tracker.load(self.path, clock)
        self.assertEqual(reloaded.entries, tracker.entries)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)


class EventTest(unittest.TestCase):
    def test_a_change_seen_by_an_event_and_then_by_a_poll_counts_once(self):
        clock = Clock()
        tracker = idle.Tracker(clock)
        tracker.poll("w1:p1", seq=18, status="working")
        clock.advance(seconds=30)
        tracker.event("w1:p1", status="idle")
        clock.advance(seconds=2)
        entry = tracker.poll("w1:p1", seq=19, status="idle")
        self.assertEqual((entry.since, entry.status, entry.seq, entry.lower_bound),
                         (NOW + timedelta(seconds=30), "idle", 19, False))

    def test_changes_between_polls_keep_the_last_events_time(self):
        clock = Clock()
        tracker = idle.Tracker(clock)
        tracker.poll("w1:p1", seq=18, status="idle")
        clock.advance(seconds=10)
        tracker.event("w1:p1", status="working")
        clock.advance(seconds=10)
        tracker.event("w1:p1", status="idle")
        clock.advance(seconds=5)
        self.assertEqual(tracker.poll("w1:p1", seq=21, status="idle").since, NOW + timedelta(seconds=20))

    def test_a_poll_that_disagrees_with_the_event_wins(self):
        clock = Clock()
        tracker = idle.Tracker(clock)
        tracker.poll("w1:p1", seq=18, status="idle")
        tracker.event("w1:p1", status="working")
        clock.advance(seconds=3)
        entry = tracker.poll("w1:p1", seq=22, status="done")
        self.assertEqual((entry.status, entry.since), ("done", NOW + timedelta(seconds=3)))

    def test_an_event_for_an_unseen_pane_is_ignored_until_polled(self):
        tracker = idle.Tracker(Clock())
        tracker.event("w1:p9", status="idle")
        self.assertEqual(tracker.entries, {})


class StaleStatusTest(unittest.TestCase):
    def test_a_status_that_disagrees_with_herdr_under_the_same_seq_is_corrected_and_keeps_its_time(self):
        # Seen on the Mac: a stale `working` saved in observed.json stayed under an unchanged seq.
        clock = Clock()
        tracker = idle.Tracker(clock)
        tracker.entries["w1:p1"] = idle.Entry(seq=7, status="working", since=NOW, lower_bound=False)
        clock.advance(minutes=4)
        entry = tracker.poll("w1:p1", seq=7, status="idle")
        self.assertEqual((entry.status, entry.since), ("idle", NOW))

    def test_an_event_ahead_of_the_poll_is_not_undone_by_it(self):
        clock = Clock()
        tracker = idle.Tracker(clock)
        tracker.poll("w1:p1", seq=7, status="idle")
        tracker.event("w1:p1", status="working")
        self.assertEqual(tracker.poll("w1:p1", seq=7, status="idle").status, "working")


class WireEventTest(unittest.TestCase):
    def test_status_events_are_read_under_either_spelling_and_others_ignored(self):
        for name in ("pane.agent_status_changed", "pane_agent_status_changed"):
            with self.subTest(name=name):
                clock = Clock()
                tracker = idle.Tracker(clock)
                tracker.poll("w1:p1", seq=18, status="idle")
                clock.advance(seconds=4)
                tracker.on_event({"event": name, "data": {"pane_id": "w1:p1", "agent_status": "working"}})
                self.assertEqual((tracker.entries["w1:p1"].status, tracker.entries["w1:p1"].since),
                                 ("working", NOW + timedelta(seconds=4)))
        tracker = idle.Tracker(Clock())
        tracker.poll("w1:p1", seq=18, status="idle")
        for event in ({"event": "pane_agent_detected", "data": {"pane_id": "w1:p1", "agent": "claude"}},
                      {"event": "pane.agent_status_changed"}, {}):
            tracker.on_event(event)
        self.assertEqual(tracker.entries["w1:p1"].status, "idle")


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
        self.assertEqual(idle.Tracker.load(self.path, clock).entries, {})
        self.path.parent.mkdir(parents=True)
        for text in ("{broken", "[]", '{"w1:p1": {"seq": 1}}', '{"w1:p1": 5}',
                     '{"w1:p1": {"seq": 1, "status": "idle", "since": "later", "lower_bound": false}}'):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                self.assertEqual(idle.Tracker.load(self.path, clock).entries, {})

    def test_the_save_is_atomic(self):
        tracker = idle.Tracker(Clock())
        tracker.poll("w1:p1", seq=1, status="idle")
        tracker.save(self.path, live_pane_ids={"w1:p1"})
        before = self.path.read_text(encoding="utf-8")
        tracker.poll("w1:p2", seq=1, status="idle")
        with unittest.mock.patch.object(idle.storage.json, "dump", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                tracker.save(self.path, live_pane_ids={"w1:p1", "w1:p2"})
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)


SAVER = """
import sys
from datetime import datetime, timezone
from pathlib import Path
from agent_parking import idle
tracker = idle.Tracker(lambda: datetime(2026, 9, 27, tzinfo=timezone.utc))
for n in range(40):
    tracker.poll("w1:p%d" % n, seq=n, status=sys.argv[2])
for _ in range(300):
    tracker.save(Path(sys.argv[1]), set(tracker.entries))
"""


class TwoDashboardsTest(unittest.TestCase):
    def test_two_processes_saving_at_once_always_leave_a_whole_file(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "observed.json"
        repository = Path(__file__).resolve().parents[1]
        savers = [subprocess.Popen([sys.executable, "-c", SAVER, str(path), status], cwd=repository)
                  for status in ("idle", "done")]
        reads = 0
        while any(saver.poll() is None for saver in savers):
            try:
                text = path.read_text()
            except FileNotFoundError:
                continue
            self.assertEqual(len(json.loads(text)), 40)  # never half a file
            reads += 1
        self.assertEqual([saver.wait() for saver in savers], [0, 0])
        self.assertGreater(reads, 0)
        self.assertEqual(sorted(p.name for p in Path(directory.name).iterdir()), ["observed.json"])


if __name__ == "__main__":
    unittest.main()
