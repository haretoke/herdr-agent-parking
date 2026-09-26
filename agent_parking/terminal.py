"""The dashboard's pane: alternate screen, hidden cursor, cbreak keys, and the loop."""

import os
import select
import signal
import sys
import termios
import time
import tty

from . import dashboard, idle, inventory


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


def run(board, terminal, poll_seconds, clock=time.monotonic, stopping=()):
    """Read the list every `poll_seconds`, draw, and read keys until q, a stop signal (an
    entry in `stopping`), or the pane going away."""
    next_poll = clock()
    while not board.quit and not stopping:
        now = clock()
        if now >= next_poll:
            board.refresh()
            next_poll = now + poll_seconds
        terminal.draw(board.lines(*terminal.size()))
        data, _ = terminal.read(max(0, next_poll - clock()))
        if data is None:
            break
        if data:
            board.on_input(data)


def stop_on_signals():
    """A list that gets an entry when SIGTERM, SIGHUP or SIGINT arrives; SIGWINCH only
    wakes the loop, which redraws at the new size."""
    stopping = []
    signal.signal(signal.SIGWINCH, lambda *_: None)
    for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(signum, lambda *_: stopping.append(True))
    return stopping


def run_dashboard(rt, own_pane_id):
    tracker = idle.Tracker.load(rt.paths.observed, rt.clock)
    board = dashboard.Dashboard(refresh=lambda: inventory.build(rt, tracker, own_pane_id))
    stopping = stop_on_signals()
    with Terminal() as terminal:
        run(board, terminal, rt.settings["poll_seconds"], stopping=stopping)
    return 0
