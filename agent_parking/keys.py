"""Keys from terminal input bytes; escape sequences may arrive split across reads."""

import codecs

ARROWS = {b"A": "up", b"B": "down", b"C": "right", b"D": "left"}
CONTROLS = {"\r": "enter", "\n": "enter", "\x7f": "backspace", "\x08": "backspace", "\x04": "ctrl-d",
            "\x03": "ctrl-c", "\x15": "ctrl-u"}


def _arrow(final):
    """The arrow a sequence's final byte stands for, as a list (empty for other keys)."""
    return [ARROWS[final]] if final in ARROWS else []


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
            kind = buffer[position + 1:position + 2]
            if kind == b"[":  # CSI: parameters, then one final byte in 0x40-0x7E
                end = position + 2
                while end < len(buffer) and not 0x40 <= buffer[end] <= 0x7E:
                    end += 1
                if end >= len(buffer):
                    self.pending = buffer[position:]
                    break
                keys.extend(_arrow(buffer[end:end + 1]))
                position = end + 1
            elif kind == b"O":  # SS3: one more byte
                if position + 2 >= len(buffer):
                    self.pending = buffer[position:]
                    break
                keys.extend(_arrow(buffer[position + 2:position + 3]))
                position += 3
            else:
                keys.append("esc")
                position += 1
        return keys

    def _text(self, byte):
        keys = []
        for ch in self.decoder.decode(byte):
            if ch in CONTROLS:
                keys.append(CONTROLS[ch])
            elif ch.isprintable():
                keys.append(ch)
        return keys
