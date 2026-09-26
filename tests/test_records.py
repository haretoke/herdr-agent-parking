import json
import os
import stat
import tempfile
import unittest
import unittest.mock
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
