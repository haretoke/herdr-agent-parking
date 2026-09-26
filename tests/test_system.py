import tempfile
import unittest
from pathlib import Path

from agent_parking import system


class ProcTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.proc = Path(self.tmp.name) / "proc"
        self.system = system.System(proc_root=self.proc)

    def put(self, pid, name, data):
        path = self.proc / str(pid) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path


class CmdlineTest(ProcTestCase):
    def test_cmdline_is_split_on_nul(self):
        self.put(42, "cmdline", b"claude\x00--resume\x00\xe3\x82\xaa\xe3\x83\xb3\x00")
        self.assertEqual(self.system.cmdline(42), ["claude", "--resume", "オン"])

    def test_a_missing_or_empty_cmdline_is_none(self):
        self.assertIsNone(self.system.cmdline(7))
        self.put(8, "cmdline", b"")
        self.assertIsNone(self.system.cmdline(8))


if __name__ == "__main__":
    unittest.main()
