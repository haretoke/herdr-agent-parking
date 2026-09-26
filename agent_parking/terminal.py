"""The dashboard's pane: alternate screen, hidden cursor, cbreak keys, and the loop."""

import os
import select
import signal
import sys
import termios
import time
import tty

from . import actions, dashboard, herdr_api, idle, inventory


class Terminal:
    def __init__(self, stdin=None, stdout=None):
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.saved = None
        self.wake = None

    def __enter__(self):
        self.saved = termios.tcgetattr(self.stdin.fileno())
        # Signals write to this pipe, so a signal ends the wait for input at once.
        self.wake = os.pipe()
        for fd in self.wake:
            os.set_blocking(fd, False)
        signal.set_wakeup_fd(self.wake[1], warn_on_full_buffer=False)
        tty.setcbreak(self.stdin.fileno())
        self.write("\x1b[?1049h\x1b[?25l\x1b[2J")
        return self

    def __exit__(self, *_):
        self.write("\x1b[?25h\x1b[?1049l")
        signal.set_wakeup_fd(-1)
        for fd in self.wake:
            os.close(fd)
        try:
            termios.tcsetattr(self.stdin.fileno(), termios.TCSADRAIN, self.saved)
        except (OSError, termios.error):
            pass  # the pane is already gone

    def write(self, text):
        try:
            self.stdout.write(text)
            self.stdout.flush()
        except OSError:
            pass

    def size(self):
        try:
            size = os.get_terminal_size(self.stdout.fileno())
        except OSError:
            return 80, 24
        return size.columns, size.lines

    def draw(self, lines):
        """The whole screen: each line cleared to its end, then everything below."""
        self.write("\x1b[H" + "\r\n".join(line + "\x1b[K" for line in lines) + "\x1b[J")

    def read(self, timeout, others=()):
        """(input bytes, the ones of `others` ready to read): b"" when there is no input,
        None once the pane is gone."""
        try:
            ready = select.select([self.stdin, self.wake[0]] + list(others), [], [], timeout)[0]
            if self.wake[0] in ready:
                os.read(self.wake[0], 1024)
            if self.stdin not in ready:
                return b"", [r for r in ready if r in others]
            data = os.read(self.stdin.fileno(), 1024)
        except OSError:
            return None, []
        return data or None, [r for r in ready if r in others]


def run(board, terminal, poll_seconds, clock=time.monotonic, stopping=(), subscribe=None):
    """Read the list every `poll_seconds`, draw, and read keys until q, a stop signal (an
    entry in `stopping`), or the pane going away. `subscribe(pane_ids)` opens the event
    stream for the listed Claude panes; when it drops, polling goes on without it."""
    next_poll = clock()
    events = Events(board, subscribe)
    try:
        while not board.quit and not stopping:
            now = clock()
            if now >= next_poll:
                board.refresh()
                next_poll = now + poll_seconds
                events.follow()
            terminal.draw(board.lines(*terminal.size()))
            if board.pending:
                board.run_pending()  # it read the list again afterwards
                next_poll = clock() + poll_seconds
                if not _drop_typed_ahead(terminal):
                    break
                continue
            data, ready = terminal.read(max(0, next_poll - clock()), events.descriptors())
            if data is None:
                break
            if ready and events.read():
                next_poll = clock()  # something changed: read the list again at once
            if data:
                board.on_input(data)
    finally:
        events.close()


def _drop_typed_ahead(terminal):
    """Throw away keys pressed while an action ran, so a q or Enter meant for the wait
    does not act on what comes after it. False when the pane is gone."""
    while True:
        data, _ = terminal.read(0)
        if data is None:
            return False
        if not data:
            return True


class Events:
    """The `events.subscribe` stream of the listed Claude panes, opened again when the
    panes change; `board.events_on` says whether it runs."""

    def __init__(self, board, subscribe):
        self.board = board
        self.subscribe = subscribe
        self.stream = None
        self.pane_ids = None

    def descriptors(self):
        return [self.stream] if self.stream is not None else []

    def follow(self):
        if self.subscribe is None:
            return
        pane_ids = [row.pane_id for row in self.board.rows if row.record is None and row.pane_id]
        if pane_ids == self.pane_ids:
            return
        self.close()
        self.pane_ids = pane_ids
        try:
            self.stream = self.subscribe(pane_ids)
        except herdr_api.HerdrError:
            self.stream = None
        self.board.events_on = self.stream is not None

    def read(self):
        """Hand the next event to the board; False when the stream ended instead."""
        try:
            event = next(self.stream)
        except (StopIteration, ValueError, OSError):
            self.close()
            self.board.events_on = False
            return False
        self.board.on_event(event)
        return True

    def close(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


def stop_on_signals():
    """A list that gets an entry when SIGTERM, SIGHUP or SIGINT arrives; SIGWINCH only
    wakes the loop, which redraws at the new size."""
    stopping = []
    signal.signal(signal.SIGWINCH, lambda *_: None)
    for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(signum, lambda *_: stopping.append(True))
    return stopping


def refresher(rt, tracker, own_pane_id):
    """The dashboard's refresh: build the list, then save the idle tracking of the live
    panes to `observed.json` (atomically, so a second dashboard never reads half a file)."""
    def refresh():
        found = inventory.build(rt, tracker, own_pane_id)
        tracker.save(rt.paths.observed, {row.pane_id for row in found.rows if row.record is None})
        return found
    return refresh


def run_dashboard(rt, own_pane_id):
    tracker = idle.Tracker.load(rt.paths.observed, rt.clock)
    board = dashboard.Dashboard(refresh=refresher(rt, tracker, own_pane_id),
                                actions=actions.Actions(rt, tracker), on_event=tracker.on_event)
    stopping = stop_on_signals()
    with Terminal() as terminal:
        run(board, terminal, rt.settings["poll_seconds"], stopping=stopping,
            subscribe=lambda pane_ids: rt.herdr.subscribe(herdr_api.status_subscriptions(pane_ids)))
    return 0
