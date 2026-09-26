import unittest

from agent_parking import argv

UUID = "2716af66-e4d8-4950-8185-97da891f78a9"
CLAUDE = "/home/u/.local/bin/claude"


class ResumeFlagsTest(unittest.TestCase):
    def test_the_executable_and_the_resume_and_naming_flags_go_and_the_rest_keeps_its_order(self):
        given = [CLAUDE, "--effort", "medium", "--resume", UUID, "--model", "x", "-c",
                 "--session-id", UUID, "--permission-mode", "auto", "--name", "work", "-n", "w2",
                 "--fork-session", "--worktree", "calltracker-inbound"]
        self.assertEqual(argv.resume_flags(given).flags,
                         ["--effort", "medium", "--model", "x", "--permission-mode", "auto",
                          "--worktree", "calltracker-inbound"])


if __name__ == "__main__":
    unittest.main()
