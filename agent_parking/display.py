"""Short texts for the dashboard's columns."""

import unicodedata


def age(seconds):
    """`12m`, `3h05m` (`2h` on the hour) or `2d`."""
    minutes = max(0, int(seconds)) // 60
    hours, minutes = divmod(minutes, 60)
    if hours >= 24:
        return "%dd" % (hours // 24)
    if hours:
        return "%dh%02dm" % (hours, minutes) if minutes else "%dh" % hours
    return "%dm" % minutes


def tokens(count):
    """`850` or `37k`."""
    return str(count) if count < 1000 else "%dk" % round(count / 1000)


def _char_width(ch):
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def width(text):
    """Terminal columns of `text` (wide and full-width characters take two)."""
    return sum(_char_width(ch) for ch in text)


def cell(text, columns):
    """`text` without control characters, cut to `columns` with `…` when it is longer."""
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cc")
    if width(text) <= columns:
        return text
    out, used = [], 0
    for ch in text:
        if used + _char_width(ch) > columns - 1:
            break
        out.append(ch)
        used += _char_width(ch)
    return "".join(out) + "…"
