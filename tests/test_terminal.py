import unittest

from agent_parking import dashboard, terminal
from agent_parking.inventory import Inventory


class FakeTerminal:
    """Reads that wait out their timeout on a fake clock, then the keys given."""

    def __init__(self, clock, idle_reads, keys=b"q"):
        self.clock = clock
        self.idle_reads = idle_reads
        self.keys = keys
        self.frames = []
        self.timeouts = []

    def size(self):
        return 80, 24

    def draw(self, lines):
        self.frames.append(lines)

    def read(self, timeout, others=()):
        self.timeouts.append(timeout)
        if self.idle_reads:
            self.idle_reads -= 1
            self.clock.now += timeout
            return b"", []
        return self.keys, []


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class PollLoopTest(unittest.TestCase):
    def test_the_list_is_read_again_every_poll_interval(self):
        clock = Clock()
        refreshes = []
        board = dashboard.Dashboard(refresh=lambda: refreshes.append(clock.now) or Inventory([], {}))
        fake = FakeTerminal(clock, idle_reads=3)
        terminal.run(board, fake, poll_seconds=2, clock=clock)
        self.assertEqual(refreshes, [100.0, 102.0, 104.0, 106.0])
        self.assertEqual(fake.timeouts, [2, 2, 2, 2])
        self.assertEqual(len(fake.frames), 4)


if __name__ == "__main__":
    unittest.main()
