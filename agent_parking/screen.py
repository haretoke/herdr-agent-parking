"""Reading Claude's screen (as `agent.read --format ansi` gives it)."""

import re

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def input_box(text):
    """`empty`, `draft` or `unknown`: what Claude's input box holds (spike 0-13)."""
    for line in reversed(text.splitlines()):
        plain = ANSI.sub("", line).rstrip("\r").strip()
        if plain.startswith("❯"):
            return "empty" if plain == "❯" else "draft"
    return "unknown"
