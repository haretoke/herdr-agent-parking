import json
import os
import stat
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timezone
from pathlib import Path

from agent_parking import records

UUID = "2716af66-e4d8-4950-8185-97da891f78a9"


def record(**fields):
    base = {"schema_version": 1, "session_id": UUID, "status": "parked", "note": None}
    base.update(fields)
    return base


class RecordsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / "state" / "records"


class WriteTest(RecordsTestCase):
    def test_a_record_is_written_under_its_uuid_with_private_permissions(self):
        old_umask = os.umask(0o022)
        self.addCleanup(os.umask, old_umask)
        path = records.write(self.dir, record())
        self.assertEqual(path, self.dir / (UUID + ".json"))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), record())
        self.assertEqual(stat.S_IMODE(self.dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_a_session_id_that_is_not_a_canonical_uuid_is_rejected_before_any_path(self):
        for bad in ["", "..", "../x", "a/b", UUID.upper(), UUID + ".json", UUID[:-1],
                    "2716af66e4d84950818597da891f78a9", " " + UUID, None, 42]:
            with self.subTest(session_id=bad):
                with self.assertRaises(ValueError):
                    records.write(self.dir, record(session_id=bad))
        self.assertFalse(self.dir.exists())

    def test_a_write_that_fails_midway_keeps_the_old_record_and_leaves_no_temp_file(self):
        path = records.write(self.dir, record(note="old"))

        def half_then_crash(obj, f, **kwargs):
            f.write('{"schema_version": 1, "sess')
            raise OSError("disk full")

        with unittest.mock.patch.object(records.json, "dump", half_then_crash):
            with self.assertRaises(OSError):
                records.write(self.dir, record(note="new"))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["note"], "old")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), [UUID + ".json"])


class NoteTest(RecordsTestCase):
    def test_a_note_with_newlines_and_control_characters_round_trips(self):
        note = "LUT の一覧を貼る前で止めた\n次: 焦点は\t色域\r\n\x1b[31mred\x1b[0m \x00   end"
        records.write(self.dir, record(note=note))
        self.assertEqual(records.list_records(self.dir)[0]["note"], note)


class WithPaneTest(unittest.TestCase):
    def test_moving_pane_id_keeps_the_old_one_in_the_history(self):
        before = record(pane_id="wD:p2T", pane_id_history=["wD:p1"])
        after = records.with_pane(before, "wD:p3A")
        self.assertEqual(after["pane_id"], "wD:p3A")
        self.assertEqual(after["pane_id_history"], ["wD:p1", "wD:p2T"])
        self.assertEqual(before["pane_id_history"], ["wD:p1"])

    def test_the_same_pane_or_a_first_pane_adds_no_history(self):
        self.assertEqual(records.with_pane(record(pane_id="wD:p2T", pane_id_history=[]), "wD:p2T")["pane_id_history"], [])
        self.assertEqual(records.with_pane(record(pane_id=None), "wD:p2T")["pane_id_history"], [])


class StartParkingTest(RecordsTestCase):
    def test_a_second_park_of_a_session_in_parking_is_refused_and_keeps_the_first(self):
        records.start_parking(self.dir, record(status="parking", note="first"))
        with self.assertRaises(records.Refused):
            records.start_parking(self.dir, record(status="parking", note="second"))
        saved = json.loads((self.dir / (UUID + ".json")).read_text(encoding="utf-8"))
        self.assertEqual(saved["note"], "first")

    def test_a_park_may_replace_a_record_that_is_not_in_parking(self):
        for status in ("parked", "park_failed", "resume_failed", "resume_pending"):
            with self.subTest(status=status):
                records.write(self.dir, record(status=status))
                records.start_parking(self.dir, record(status="parking", note=status))
                saved = json.loads((self.dir / (UUID + ".json")).read_text(encoding="utf-8"))
                self.assertEqual((saved["status"], saved["note"]), ("parking", status))

    def test_the_flow_itself_may_move_its_record_from_parking_to_parked(self):
        records.start_parking(self.dir, record(status="parking"))
        records.write(self.dir, record(status="parked"))
        saved = json.loads((self.dir / (UUID + ".json")).read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "parked")


class VanishingTest(RecordsTestCase):
    def test_files_that_vanish_while_listing_are_skipped(self):
        other = "5e0c1f2a-0000-4000-8000-000000000001"
        records.write(self.dir, record())
        gone = self.dir / (other + ".json")  # settled by another dashboard after the directory was read
        real = records._record_files
        with unittest.mock.patch.object(records, "_record_files",
                                        side_effect=lambda d: real(d) + ([gone] if d == self.dir else [])):
            self.assertEqual([r["session_id"] for r in records.list_records(self.dir)], [UUID])


class ForgetTest(RecordsTestCase):
    def test_forget_deletes_the_record_or_its_broken_file_and_nothing_else(self):
        other = "5e0c1f2a-0000-4000-8000-000000000001"
        records.write(self.dir, record())
        records.write(self.dir, record(session_id=other))
        (self.dir / "broken").mkdir()
        (self.dir / "broken" / (other + ".json")).write_text("{")
        records.forget(self.dir, UUID)
        records.forget(self.dir, other)
        self.assertEqual(sorted(p.name for p in self.dir.rglob("*") if p.is_file()), [])
        records.forget(self.dir, UUID)  # already gone: nothing to do


class ResumedTest(RecordsTestCase):
    NOW = datetime(2026, 9, 27, 12, 0, 0, tzinfo=timezone.utc)

    def setUp(self):
        super().setUp()
        self.resumed = self.dir.parent / "resumed"

    def test_a_resumed_record_moves_to_resumed_with_its_time(self):
        records.write(self.dir, record(status="parked"))
        self.assertTrue(records.mark_resumed(self.dir, self.resumed, UUID, self.NOW))
        self.assertFalse((self.dir / (UUID + ".json")).exists())
        moved = json.loads((self.resumed / (UUID + ".json")).read_text(encoding="utf-8"))
        self.assertEqual((moved["status"], moved["resumed_at"]), ("resumed", "2026-09-27T12:00:00Z"))
        self.assertEqual(stat.S_IMODE(self.resumed.stat().st_mode), 0o700)

    def test_a_record_already_moved_by_someone_else_is_not_an_error(self):
        self.assertFalse(records.mark_resumed(self.dir, self.resumed, UUID, self.NOW))
        self.assertFalse(self.resumed.exists())

    def test_resumed_records_are_deleted_after_the_retention_only(self):
        keep_days = 30
        records.write(self.resumed, record(status="resumed", resumed_at="2026-08-28T12:00:01Z"))
        records.write(self.resumed, record(session_id=OTHER, status="resumed", resumed_at="2026-08-28T11:59:59Z"))
        records.write(self.resumed, record(session_id=THIRD, status="resumed", resumed_at="not a time"))
        deleted = records.purge_resumed(self.resumed, keep_days, self.NOW)
        self.assertEqual(deleted, [OTHER])
        self.assertEqual(sorted(p.name for p in self.resumed.iterdir()), sorted([UUID + ".json", THIRD + ".json"]))

    def test_an_unknown_schema_is_never_moved_nor_deleted(self):
        text = json.dumps({"schema_version": 2, "session_id": UUID, "status": "parked"})
        self.dir.mkdir(parents=True)
        (self.dir / (UUID + ".json")).write_text(text, encoding="utf-8")
        with self.assertRaises(records.Refused):
            records.mark_resumed(self.dir, self.resumed, UUID, self.NOW)
        self.assertEqual((self.dir / (UUID + ".json")).read_text(encoding="utf-8"), text)
        self.resumed.mkdir(parents=True)
        old = json.dumps({"schema_version": 2, "session_id": OTHER, "resumed_at": "2000-01-01T00:00:00Z"})
        (self.resumed / (OTHER + ".json")).write_text(old, encoding="utf-8")
        self.assertEqual(records.purge_resumed(self.resumed, 30, self.NOW), [])
        self.assertTrue((self.resumed / (OTHER + ".json")).exists())


OTHER = "0939a1b4-2ecb-4bd4-a241-59bd6732651f"
THIRD = "a528d90c-d0d6-404a-a9ee-373de7435e3c"


class ListTest(RecordsTestCase):
    def test_broken_json_moves_to_broken_and_is_listed_as_a_broken_record(self):
        records.write(self.dir, record())
        (self.dir / (OTHER + ".json")).write_text("{not json", encoding="utf-8")
        (self.dir / (THIRD + ".json")).write_text("[1, 2]", encoding="utf-8")
        for attempt in (1, 2):
            with self.subTest(listing=attempt):
                listed = records.list_records(self.dir)
                self.assertEqual([r["session_id"] for r in listed if r["status"] != "broken"], [UUID])
                broken = sorted(r["session_id"] for r in listed if r["status"] == "broken")
                self.assertEqual(broken, sorted([OTHER, THIRD]))
                self.assertEqual(sorted(p.name for p in (self.dir / "broken").iterdir()),
                                 sorted([OTHER + ".json", THIRD + ".json"]))
                self.assertFalse((self.dir / (OTHER + ".json")).exists())

    def test_a_record_with_an_unknown_schema_version_is_neither_listed_nor_touched(self):
        records.write(self.dir, record())
        future = self.dir / (OTHER + ".json")
        text = json.dumps({"schema_version": 2, "session_id": OTHER, "status": "parked"})
        future.write_text(text, encoding="utf-8")
        (self.dir / (THIRD + ".json")).write_text(json.dumps({"session_id": THIRD}), encoding="utf-8")
        self.assertEqual([r["session_id"] for r in records.list_records(self.dir)], [UUID])
        with self.assertRaises(records.Refused):
            records.write(self.dir, record(session_id=OTHER))
        self.assertEqual(future.read_text(encoding="utf-8"), text)
        self.assertFalse((self.dir / "broken").exists())

    def test_an_empty_or_missing_directory_lists_nothing(self):
        self.assertEqual(records.list_records(self.dir), [])


if __name__ == "__main__":
    unittest.main()
