"""The dashboard's screen and keys, free of terminal and socket I/O (the loop that
drives it is in `terminal`)."""

from . import display, keys, table

KEYS = ("s park  c compact  C compact+park  r resume  R swap  g go  S idle≥60m  n note  x forget  "
        "/ filter  ? help  q quit")

MOVES = {"j": 1, "down": 1, "k": -1, "up": -1}


class Dashboard:
    def __init__(self, refresh, on_event=lambda event: None):
        self._refresh = refresh   # () -> inventory.Inventory
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
        inventory = self._refresh()
        self.rows, self.others = inventory.rows, inventory.others

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
        footer = [rule, " " + ("events: off · " if not self.events_on else "") + KEYS]
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
            if key == "q":
                self.quit = True
            elif key == "i":
                self.show_detail = not self.show_detail
            elif key in MOVES:
                self.selected = max(0, min(len(self.rows) - 1, self.selected + MOVES[key]))

    def on_event(self, event):
        self._on_event(event)
