import json
import os
import stat
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
