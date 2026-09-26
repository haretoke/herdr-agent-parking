"""Short texts for the dashboard's columns."""


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
