"""The dashboard's screen and keys, free of terminal and socket I/O (the loop that
drives it is in `terminal`)."""

from . import display, keys, ready, table

KEYS = ("s park  c compact  C compact+park  r resume  R swap  g go  S idle≥60m  n note  x forget  "
        "/ filter  ? help  q quit")

MOVES = {"j": 1, "down": 1, "k": -1, "up": -1}


def _key(row):
    return row.session_id or row.pane_id


class Dashboard:
    def __init__(self, refresh, actions=None, on_event=lambda event: None):
        self._refresh = refresh   # () -> inventory.Inventory
        self.actions = actions    # what the keys do (actions.Actions)
        self.message = ""
        self.dialog = None
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
        footer = ([rule] + ([" " + self.message] if self.message else []) +
                  [" " + ("events: off · " if not self.events_on else "") + KEYS])
        top = [self.title(), rule, table.header(width)]
        body = self._visible_body(width, max(1, height - len(top) - len(footer)))
        return [display.cell(line, width) for line in top + body + footer]

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
        self.message = self._refusal(self._row(), "park") or ""

    def _go(self):
        row = self._row()
        if row is None or not row.pane_id:
            self.message = "no pane for this row"
            return
        self.actions.focus(row.pane_id)
        self.quit = True

    def on_event(self, event):
        self._on_event(event)
