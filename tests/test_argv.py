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


    def test_the_equals_form_and_the_short_form_are_removed_too(self):
        cases = [
            [CLAUDE, "--resume=" + UUID, "--model", "x"],
            [CLAUDE, "-r", UUID, "--model", "x"],
            [CLAUDE, "--session-id=" + UUID, "--name=work", "--model", "x"],
            [CLAUDE, "--resume", "--model", "x"],
            [CLAUDE, "--model", "x", "--resume"],
        ]
        for given in cases:
            with self.subTest(argv=given):
                self.assertEqual(argv.resume_flags(given).flags, ["--model", "x"])

    def test_an_equals_form_of_a_kept_flag_stays_as_one_token(self):
        self.assertEqual(argv.resume_flags([CLAUDE, "--model=x", "-r=" + UUID]).flags, ["--model=x"])


    def test_a_value_taking_flag_at_the_end_without_its_value_does_not_crash(self):
        for given, expected in [
            ([CLAUDE, "--model", "x", "--name"], ["--model", "x"]),
            ([CLAUDE, "--session-id"], []),
            ([CLAUDE, "-n"], []),
            ([CLAUDE], []),
            ([], []),
        ]:
            with self.subTest(argv=given):
                self.assertEqual(argv.resume_flags(given).flags, expected)


if __name__ == "__main__":
    unittest.main()
