"""The dashboard's dialogs: text input and confirmations. Keys come from `keys.KeyParser`;
`on_key` returns `("done", text)`, `("cancel", None)` or None while the dialog stays open."""

CANCEL = ("cancel", None)


class TextInput:
    """One line, or with `multiline` several: Enter starts a new line, and a blank line or
    Ctrl-D ends the text (a note; Enter at once means none)."""

    def __init__(self, lines, initial="", multiline=False):
        self.prompt = list(lines)
        self.multiline = multiline
        self.rows = (initial or "").split("\n") if multiline else [initial or ""]

    def lines(self):
        return self.prompt + ["> " + row for row in self.rows]

    def _done(self):
        return ("done", "\n".join(self.rows).rstrip("\n"))

    def on_key(self, key):
        if key in ("esc", "ctrl-c"):
            return CANCEL
        if key == "ctrl-d" and self.multiline:
            return self._done()
        if key == "enter":
            if not self.multiline or self.rows[-1] == "":
                return self._done()
            self.rows.append("")
        elif key == "backspace":
            if self.rows[-1] or len(self.rows) == 1:
                self.rows[-1] = self.rows[-1][:-1]
            else:
                self.rows.pop()
        elif key == "ctrl-u":
            self.rows[-1] = ""
        elif len(key) == 1:
            self.rows[-1] += key
        return None


class Confirm:
    """Lines to read and the keys that choose (`{"enter": "yes", "e": "edit"}`); Esc
    cancels. With `others_cancel` any other key cancels too (a `(y/N)` question)."""

    def __init__(self, lines, choices, others_cancel=False):
        self.shown = list(lines)
        self.choices = dict(choices)
        self.others_cancel = others_cancel

    def lines(self):
        return self.shown

    def on_key(self, key):
        if key in self.choices:
            return ("done", self.choices[key])
        if key in ("esc", "ctrl-c") or self.others_cancel:
            return CANCEL
        return None
