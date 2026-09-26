"""The dashboard's dialogs: text input and confirmations. Keys come from `keys.KeyParser`;
`on_key` returns `("done", text)`, `("cancel", None)` or None while the dialog stays open."""

CANCEL = ("cancel", None)


class TextInput:
    def __init__(self, lines, initial=""):
        self.prompt = list(lines)
        self.text = initial

    def lines(self):
        return self.prompt + ["> " + self.text]

    def on_key(self, key):
        if key in ("esc", "ctrl-c"):
            return CANCEL
        if key == "enter":
            return ("done", self.text)
        if key == "backspace":
            self.text = self.text[:-1]
        elif key == "ctrl-u":
            self.text = ""
        elif len(key) == 1:
            self.text += key
        return None
