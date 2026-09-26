"""Reading Claude's screen (as `agent.read --format ansi` gives it)."""

import re

SGR = re.compile(r"\x1b\[([0-9;]*)m")


def _plain(line):
    return SGR.sub("", line).replace("\r", "").strip()


def _is_rule(line):
    plain = _plain(line)
    return plain != "" and set(plain) == {"─"}


def _typed(line):
    """The characters of `line` after `❯` that are not dim (the placeholder is dim)."""
    typed, dim, pos = [], False, 0
    for match in SGR.finditer(line):
        if not dim:
            typed.append(line[pos:match.start()])
        for param in (match.group(1) or "0").split(";"):
            if param in ("", "0", "22"):
                dim = False
            elif param == "2":
                dim = True
        pos = match.end()
    if not dim:
        typed.append(line[pos:])
    text = "".join(typed).replace("\r", "")
    return text[text.index("❯") + 1:].strip() if "❯" in text else text.strip()


def input_box(text):
    """What Claude's input box holds: `empty`, `draft`, or `unknown` when no `❯` line sits
    between two `─` rules (spike 0-13)."""
    lines = text.split("\n")
    for i in range(len(lines) - 2, 0, -1):
        if _plain(lines[i]).startswith("❯") and _is_rule(lines[i - 1]) and _is_rule(lines[i + 1]):
            return "draft" if _typed(lines[i]) else "empty"
    return "unknown"
