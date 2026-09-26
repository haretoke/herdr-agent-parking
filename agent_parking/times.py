"""Timestamps as the records and Claude's transcripts write them (UTC, `Z`)."""

from datetime import datetime, timezone


def iso(moment):
    """`moment` (an aware datetime) as UTC text, `2026-09-27T12:00:00Z`."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(text):
    """`2026-09-26T16:39:48.863Z` (fraction optional) as an aware datetime, or None."""
    for layout in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(text, layout).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
    return None
