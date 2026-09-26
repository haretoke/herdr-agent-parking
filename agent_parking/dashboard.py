"""The dashboard's screen and keys, free of terminal and socket I/O (the loop that
drives it is in `terminal`)."""

import textwrap

from . import dialogs, display, keys, park, ready, recreate, resume, table

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
        self.filter = ""
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
        chosen = self._row()
        inventory = self._refresh()
        self.rows, self.others = inventory.rows, inventory.others
        self._keep(_key(chosen) if chosen else None)

    def _keep(self, chosen):
        """Select the row of `chosen` among the visible ones, else the nearest one left."""
        keys = [_key(row) for row in self.visible()]
        if chosen in keys:
            self.selected = keys.index(chosen)
        self.selected = max(0, min(self.selected, len(keys) - 1))

    def visible(self):
        """The rows shown and selectable: those matching the filter (`/`) in their name,
        cwd or labels, ignoring case."""
        wanted = self.filter.lower()
        return [row for row in self.rows if not wanted or any(
            wanted in (text or "").lower()
            for text in (row.name, row.cwd, row.label, row.tab_label, row.workspace_label))]

    def title(self):
        running = [row for row in self.rows if row.record is None]
        parts = ["Agent parking", "%d claude" % len(running)]
        memory = sum(row.rss_kb or 0 for row in running)
        if memory:
            parts.append(table.memory(memory))
        parts.extend("%s: %d (not managed)" % (agent, count) for agent, count in sorted(self.others.items()))
        if self.filter:
            parts.append("filter: " + self.filter)
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
        for index, row in enumerate(self.visible()):
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
                self.selected = max(0, min(len(self.visible()) - 1, self.selected + MOVES[key]))
            elif key == "g":
                self._go()
            elif key == "s":
                self._park()
            elif key == "x":
                self._forget()
            elif key == "n":
                self._edit_note()
            elif key == "r":
                self._resume()
            elif key == "R":
                self._swap()
            elif key == "/":
                self._ask(dialogs.TextInput(["filter by name, cwd or label (empty shows all):"], initial=self.filter),
                          self._set_filter)

    def _row(self):
        rows = self.visible()
        return rows[self.selected] if rows else None

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

    def _parked_row(self):
        """The selected row when it has a park record; else None and a message."""
        row = self._row()
        if row is None or row.record is None:
            self.message = "no record for this row"
            return None
        return row

    def _forget(self):
        row = self._parked_row()
        if row is None:
            return
        question = 'forget the record of %s "%s"? The transcript stays. (y/N)' % (
            row.pane_id or "(no pane)", row.name or "")
        self._ask(dialogs.Confirm([question], {"y": "yes"}, others_cancel=True),
                  lambda _: self._later("forgetting…", lambda: self.actions.forget(row.session_id) or
                                        "forgot the record of %s" % row.session_id[:8]))

    def _edit_note(self):
        row = self._parked_row()
        if row is None:
            return
        prompt = ['note for %s "%s" (a blank line or Ctrl-D ends it):' % (row.pane_id or "(no pane)", row.name or "")]
        self._ask(dialogs.TextInput(prompt, initial=row.record.get("note") or "", multiline=True),
                  lambda note: self._later("saving the note…", lambda: self.actions.set_note(row.session_id, note)
                                           or "note saved"))

    def _resume(self):
        row = self._parked_row()
        if row is not None:
            self._confirm_resume(row)

    def _confirm_resume(self, row):
        lines = resume.confirmation(row.record, self.actions.now())
        self._ask(dialogs.Confirm(lines, {"enter": "yes", "e": "edit"}),
                  lambda choice: self._edit_before_resume(row) if choice == "edit"
                  else self._start_resume(row, False))

    def _edit_before_resume(self, row):
        """`e` in the resume confirmation: save the edited note, then confirm again."""
        def save(note):
            self.actions.set_note(row.session_id, note)
            row.record = dict(row.record, note=note if note.strip() else None)
            self._confirm_resume(row)
        self._ask(dialogs.TextInput(["note (a blank line or Ctrl-D ends it):"], initial=row.record.get("note") or "",
                                    multiline=True), save)

    def _start_resume(self, row, new_workspace):
        self._later("resuming %s…" % (row.pane_id or row.session_id[:8]),
                    lambda: self._resumed(row, self.actions.resume(row.session_id, new_workspace)))

    def _resumed(self, row, outcome):
        """The message for a resume, or the question whether to open a new workspace
        when the session's own is gone."""
        if outcome.kind == "refused" and outcome.message == recreate.NEEDS_WORKSPACE:
            self._ask(dialogs.Confirm([outcome.message + " (y/N)"], {"y": "yes"}, others_cancel=True),
                      lambda _: self._start_resume(row, True))
            return ""
        return _said(outcome, (outcome.record or {}).get("pane_id") or row.pane_id or "(new pane)")

    def _swap(self):
        """`R`: park and resume at once, so the session restarts on the current `claude`;
        asks first when that would not change the version (or it is unknown)."""
        row = self._row()
        self.message = self._refusal(row, "swap") or ""
        if self.message:
            return

        def start(_=None):
            self._later("swapping %s (park, then resume)…" % row.pane_id,
                        lambda: self._swapped(row, *self.actions.swap(row.pane_id)))

        question = resume.swap_question(row.version, row.current_version)
        if question is None:
            start()
        else:
            self._ask(dialogs.Confirm([question], {"y": "yes"}, others_cancel=True), start)

    def _swapped(self, row, parked, resumed):
        if resumed is None:
            return _said(parked, row.pane_id)
        return _said(resumed, (resumed.record or {}).get("pane_id") or row.pane_id)

    def _set_filter(self, text):
        chosen = self._row()
        self.filter = text.strip()
        self._keep(_key(chosen) if chosen else None)

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
