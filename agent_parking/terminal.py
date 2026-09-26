"""The dashboard's pane: alternate screen, hidden cursor, cbreak keys, and the loop."""

import os
import select
import signal
import sys
import termios
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

    def read(self, timeout):
        """Input bytes, b"" when there is none, or None once the pane is gone."""
        try:
            ready = select.select([self.stdin, self.wake[0]], [], [], timeout)[0]
            if self.wake[0] in ready:
                os.read(self.wake[0], 1024)
            if self.stdin not in ready:
                return b""
            data = os.read(self.stdin.fileno(), 1024)
        except OSError:
            return None
        return data or None


def run(board, terminal, poll_seconds):
    """Draw and read keys until q, a stop signal, or the pane going away."""
    stopping = []
    signal.signal(signal.SIGWINCH, lambda *_: None)  # wakes the loop, which redraws at the new size
    for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(signum, lambda *_: stopping.append(True))
    while not board.quit and not stopping:
        terminal.draw(board.lines(*terminal.size()))
        data = terminal.read(poll_seconds)
        if data is None:
            break
        if data:
            board.on_input(data)


def run_dashboard(rt, own_pane_id):
    tracker = idle.Tracker.load(rt.paths.observed, rt.clock)
    board = dashboard.Dashboard(refresh=lambda: inventory.build(rt, tracker, own_pane_id))
    board.refresh()
    with Terminal() as terminal:
        run(board, terminal, rt.settings["poll_seconds"])
    return 0
