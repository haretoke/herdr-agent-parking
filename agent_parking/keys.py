"""Keys from terminal input bytes; escape sequences may arrive split across reads."""

import codecs

ARROWS = {b"A": "up", b"B": "down", b"C": "right", b"D": "left"}
CONTROLS = {"\r": "enter", "\n": "enter", "\x7f": "backspace", "\x08": "backspace", "\x04": "ctrl-d",
            "\x03": "ctrl-c", "\x15": "ctrl-u"}


class KeyParser:
    def __init__(self):
        self.pending = b""
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def feed(self, data):
        """The keys in `data`: characters as themselves, arrows as `up` / `down` / ..., and
        `enter`, `esc`, `backspace`, `ctrl-d`, `ctrl-c`, `ctrl-u`. A lone ESC at the end of a
        read is the Esc key (terminals send a whole arrow sequence in one write)."""
        keys = []
        buffer = self.pending + data
        self.pending = b""
        position = 0
        while position < len(buffer):
            byte = buffer[position:position + 1]
            if byte != b"\x1b":
                keys.extend(self._text(byte))
                position += 1
                continue
            sequence = buffer[position:position + 3]
            if sequence == b"\x1b":
                keys.append("esc")
                break
            if sequence[1:2] not in (b"[", b"O"):
                keys.append("esc")
                position += 1
                continue
            if len(sequence) < 3:
                self.pending = sequence
                break
            if sequence[2:3] in ARROWS:
                keys.append(ARROWS[sequence[2:3]])
            position += 3
        return keys

    def _text(self, byte):
        keys = []
        for ch in self.decoder.decode(byte):
            if ch in CONTROLS:
                keys.append(CONTROLS[ch])
            elif ch.isprintable():
                keys.append(ch)
        return keys
