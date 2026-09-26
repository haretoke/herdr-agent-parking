import unittest

from agent_parking import dashboard, herdr_api, terminal
from agent_parking.inventory import Inventory, Row


class FakeTerminal:
    """Reads that follow `steps`: (seconds to pass, or None to wait out the timeout; the
    input; the other descriptors ready)."""

    def __init__(self, clock, steps):
        self.clock = clock
        self.steps = list(steps)
        self.frames = []
        self.timeouts = []

    def size(self):
        return 80, 24

    def draw(self, lines):
        self.frames.append(lines)

    def read(self, timeout, others=()):
        self.timeouts.append(timeout)
        seconds, data, ready = self.steps.pop(0)
        self.clock.now += timeout if seconds is None else seconds
        return data, [r for r in ready if r in others]


def waits(count):
    return [(None, b"", [])] * count + [(0, b"q", [])]


class FakeSubscription:
    def __init__(self, events=()):
        self.events = list(events)
        self.closed = False

    def __next__(self):
        if not self.events:
            raise StopIteration
        return self.events.pop(0)

    def close(self):
        self.closed = True


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
        fake = FakeTerminal(clock, waits(3))
        terminal.run(board, fake, poll_seconds=2, clock=clock)
        self.assertEqual(refreshes, [100.0, 102.0, 104.0, 106.0])
        self.assertEqual(fake.timeouts, [2, 2, 2, 2])
        self.assertEqual(len(fake.frames), 4)


class DroppedEventsTest(unittest.TestCase):
    def test_a_dropped_subscription_is_closed_and_polling_goes_on_with_events_off(self):
        clock = Clock()
        refreshes = []
        board = dashboard.Dashboard(refresh=lambda: refreshes.append(clock.now) or
                                    Inventory([Row(pane_id="w1:p2", status="idle")], {}))
        subscription = FakeSubscription()
        subscribed = []

        def subscribe(pane_ids):
            subscribed.append(pane_ids)
            return subscription

        fake = FakeTerminal(clock, [(0.5, b"", [subscription]), (None, b"", []), (0, b"q", [])])
        terminal.run(board, fake, poll_seconds=2, clock=clock, subscribe=subscribe)
        self.assertEqual(subscribed, [["w1:p2"]])
        self.assertTrue(subscription.closed)
        self.assertEqual(refreshes, [100.0, 102.0])
        self.assertTrue(fake.frames[-1][-1].startswith(" events: off · s park"), fake.frames[-1][-1])


    def test_a_refused_subscription_leaves_events_off(self):
        clock = Clock()
        board = dashboard.Dashboard(refresh=lambda: Inventory([Row(pane_id="w1:p2", status="idle")], {}))

        def subscribe(pane_ids):
            raise herdr_api.HerdrError("no", "invalid_request")

        fake = FakeTerminal(clock, waits(1))
        terminal.run(board, fake, poll_seconds=2, clock=clock, subscribe=subscribe)
        self.assertFalse(board.events_on)
        self.assertEqual(len(fake.frames), 2)


if __name__ == "__main__":
    unittest.main()
