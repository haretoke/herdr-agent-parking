"""The dashboard's screen and keys, free of terminal and socket I/O (the loop that
drives it is in `terminal`)."""

import textwrap

from . import dialogs, display, keys, park, ready, table

KEYS = ("s park  c compact  C compact+park  r resume  R swap  g go  S idle≥60m  n note  x forget  "
        "/ filter  ? help  q quit")

MOVES = {"j": 1, "down": 1, "k": -1, "up": -1}


def _said(outcome, pane_id):
    """The message for a flow's outcome."""
    text = "%s %s" % (outcome.kind.replace("_", " "), pane_id)
    return text + (": " + outcome.message if outcome.message else "")


def _key(row):
    return row.session_id or row.pane_id


class Dashboard:
    def __init__(self, refresh, actions=None, on_event=lambda event: None):
        self._refresh = refresh   # () -> inventory.Inventory
        self.actions = actions    # what the keys do (actions.Actions)
        self.message = ""
        self.dialog = None
        self.on_done = None   # what the open dialog's answer goes to
        self.pending = None   # (what to show while it runs, the call): run by the loop after a draw
        self._on_event = on_event  # a Herdr event, before the list is read again
        self.rows = []
        self.others = {}
        self.selected = 0
        self.top = 0  # the first body line in view
        self.show_detail = True
        self.keys = keys.KeyParser()
        self.quit = False
        self.events_on = True

    def refresh(self):
        """Read the list again; the selection stays on its session (or pane) wherever the
        row moved, else on the nearest row left."""
        chosen = _key(self.rows[self.selected]) if self.rows else None
        inventory = self._refresh()
        self.rows, self.others = inventory.rows, inventory.others
        keys = [_key(row) for row in self.rows]
        if chosen in keys:
            self.selected = keys.index(chosen)
        self.selected = max(0, min(self.selected, len(self.rows) - 1))

    def title(self):
        running = [row for row in self.rows if row.record is None]
        parts = ["Agent parking", "%d claude" % len(running)]
        memory = sum(row.rss_kb or 0 for row in running)
        if memory:
            parts.append(table.memory(memory))
        parts.extend("%s: %d (not managed)" % (agent, count) for agent, count in sorted(self.others.items()))
        return " " + " · ".join(parts)

    def lines(self, width, height):
        rule = " " + "─" * (width - 2)
        footer = [rule] + self._footer(width)
        top = [self.title(), rule, table.header(width)]
        body = self._visible_body(width, max(1, height - len(top) - len(footer)))
        return [display.cell(line, width) for line in top + body + footer]

    def _footer(self, width):
        """The open dialog (wrapped to the width), else the message and the keys."""
        if self.dialog is not None:
            return [" " + part for line in self.dialog.lines()
                    for part in (textwrap.wrap(line, width - 1) if display.width(line) > width - 1 else [line])]
        message = self.pending[0] if self.pending else self.message
        return (([" " + message] if message else []) +
                [" " + ("events: off · " if not self.events_on else "") + KEYS])

    def _visible_body(self, width, space):
        """The rows' lines that fit in `space`, scrolled only as far as needed to keep the
        selected row and its detail line in view."""
        body, first, last = [], 0, 0
        for index, row in enumerate(self.rows):
            cells = table.cells(row)
            if index == self.selected:
                first = len(body)
            body.append(table.line(cells, width, selected=index == self.selected))
            if index == self.selected and self.show_detail:
                note = (row.record or {}).get("note")
                body.extend(line for line in [table.detail(cells, note, width)] if line)
            if index == self.selected:
                last = len(body) - 1
        self.top = min(self.top, first)
        self.top = max(self.top, last - space + 1, 0)
        return body[self.top:self.top + space]

    def on_input(self, data):
        for key in self.keys.feed(data):
            if self.dialog is not None:
                self._answer(key)
                continue
            self.message = ""
            if key == "q":
                self.quit = True
            elif key == "i":
                self.show_detail = not self.show_detail
            elif key in MOVES:
                self.selected = max(0, min(len(self.rows) - 1, self.selected + MOVES[key]))
            elif key == "g":
                self._go()
            elif key == "s":
                self._park()

    def _row(self):
        return self.rows[self.selected] if self.rows else None

    def _refusal(self, row, action):
        """Why `action` cannot start on `row` (None when it can): the same statuses as the
        park and compact flows check again before acting."""
        if row is None:
            return "no session selected"
        if row.record is not None:
            return "cannot %s: already parked" % action
        if row.status not in ready.READY_STATUSES:
            return "cannot %s: Claude is %s" % (action, row.status or "unknown")
        return None

    def _park(self):
        row = self._row()
        self.message = self._refusal(row, "park") or ""
        if self.message:
            return
        self._ask(dialogs.TextInput(park.confirmation(row), multiline=True),
                  lambda note: self._later("parking %s…" % row.pane_id,
                                           lambda: _said(self.actions.park(row.pane_id, note), row.pane_id)))

    def _ask(self, dialog, on_done):
        self.dialog, self.on_done = dialog, on_done

    def _answer(self, key):
        result = self.dialog.on_key(key)
        if result is None:
            return
        kind, value = result
        self.dialog = None
        if kind == "done":
            self.on_done(value)

    def _later(self, message, call):
        """Run `call` (it may wait for Claude) once the loop has drawn `message`; its
        return value becomes the message."""
        self.pending = (message, call)

    def run_pending(self):
        _, call = self.pending
        self.pending = None
        self.message = call()
        self.refresh()

    def _go(self):
        row = self._row()
        if row is None or not row.pane_id:
            self.message = "no pane for this row"
            return
        self.actions.focus(row.pane_id)
        self.quit = True

    def on_event(self, event):
        self._on_event(event)
