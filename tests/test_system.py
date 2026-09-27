import subprocess
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


class ExeTest(ProcTestCase):
    def test_exe_is_the_link_target_or_none(self):
        (self.proc / "42").mkdir(parents=True)
        (self.proc / "42" / "exe").symlink_to("/home/node/.local/share/claude/versions/2.1.281")
        self.assertEqual(self.system.exe(42), "/home/node/.local/share/claude/versions/2.1.281")
        self.assertIsNone(self.system.exe(7))

    def test_proc_is_there_only_when_its_root_is_a_directory(self):
        self.assertFalse(self.system.has_proc())
        self.proc.mkdir()
        self.assertTrue(self.system.has_proc())


class RssTest(ProcTestCase):
    def test_linux_reads_vmrss_in_kib(self):
        self.put(42, "status", b"Name:\tclaude\nVmPeak:\t 500000 kB\nVmRSS:\t  209920 kB\nThreads:\t12\n")
        self.assertEqual(self.system.rss_kb(42), 209920)

    def test_without_proc_ps_is_asked(self):
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, stdout="  197632\n", stderr="")

        self.assertEqual(system.System(proc_root=self.proc, run=run).rss_kb(42), 197632)
        self.assertEqual(calls, [["ps", "-o", "rss=", "-p", "42"]])

    def test_every_failure_is_none(self):
        self.proc.mkdir()
        self.put(43, "status", b"Name:\tzombie\n")
        self.assertIsNone(self.system.rss_kb(42))
        self.assertIsNone(self.system.rss_kb(43))

        def gone(args, **kwargs):
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

        def missing(args, **kwargs):
            raise FileNotFoundError("ps")

        for run in (gone, missing):
            with self.subTest(run=run.__name__):
                self.assertIsNone(system.System(proc_root=self.tmp.name + "/none", run=run).rss_kb(42))


class RssManyTest(ProcTestCase):
    def test_without_proc_one_ps_call_reads_every_pid(self):
        # Seen on the Mac: one ps per pid, about 27 every 2 s for nine sessions.
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, stdout="   42  197632\n   43   8000\n", stderr="")

        found = system.System(proc_root=self.proc, run=run).rss_many([42, 43, 44])
        self.assertEqual(found, {42: 197632, 43: 8000})
        self.assertEqual(calls, [["ps", "-o", "pid=,rss=", "-p", "42,43,44"]])
        self.assertEqual(system.System(proc_root=self.proc, run=run).rss_many([]), {})
        self.assertEqual(len(calls), 1)

    def test_linux_reads_each_status_and_failures_leave_pids_out(self):
        self.proc.mkdir()
        self.put(42, "status", b"VmRSS:\t  209920 kB\n")
        self.assertEqual(self.system.rss_many([42, 43]), {42: 209920})

        def missing(args, **kwargs):
            raise FileNotFoundError("ps")

        self.assertEqual(system.System(proc_root=self.tmp.name + "/none", run=missing).rss_many([42]), {})


if __name__ == "__main__":
    unittest.main()
