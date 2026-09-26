"""The dashboard's screen and keys, free of terminal and socket I/O (the loop that
drives it is in `terminal`)."""

from . import display, table

KEYS = ("s park  c compact  C compact+park  r resume  R swap  g go  S idle≥60m  n note  x forget  "
        "/ filter  ? help  q quit")


class Dashboard:
    def __init__(self, refresh):
        self._refresh = refresh   # () -> inventory.Inventory
        self.rows = []
        self.others = {}
        self.selected = 0

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
        body = [table.line(table.cells(row), width, selected=index == self.selected)
                for index, row in enumerate(self.rows)]
        screen = [self.title(), rule, table.header(width)] + body + [rule, " " + KEYS]
        return [display.cell(line, width) for line in screen]
