import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
