"""How long each Claude pane has been in its status. Herdr gives no times (only
`state_change_seq`), so the dashboard tracks them itself."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from . import display, storage, times


@dataclass
class Entry:
    seq: Optional[int]
    status: Optional[str]
    since: datetime
    lower_bound: bool
    from_event: bool = False


class Tracker:
    def __init__(self, clock, summary_for):
        self.clock = clock
        self.summary_for = summary_for
        self.entries = {}

    @classmethod
    def load(cls, path, clock, summary_for):
        """A tracker with the entries saved at `path`; a missing or broken file (or entry)
        starts empty, since the tracking only helps."""
        tracker = cls(clock, summary_for)
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            for pane_id, raw in saved.items():
                since = times.parse(raw["since"])
                if since is None:
                    raise ValueError("bad time")
                tracker.entries[pane_id] = Entry(raw["seq"], raw["status"], since, bool(raw["lower_bound"]))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            tracker.entries = {}
        return tracker

    def save(self, path, live_pane_ids):
        """Drop the entries of panes that are gone, then write the rest to `path`."""
        self.entries = {k: v for k, v in self.entries.items() if k in live_pane_ids}
        storage.write_json(path, {k: {"seq": v.seq, "status": v.status, "since": times.iso(v.since),
                                      "lower_bound": v.lower_bound} for k, v in self.entries.items()})

    def poll(self, pane_id, seq, status):
        """Record what `agent.list` says about `pane_id` now; returns its entry."""
        entry = self.entries.get(pane_id)
        if entry is None:
            entry = self._first(seq, status, self.summary_for(pane_id))
            self.entries[pane_id] = entry
        elif seq != entry.seq:
            if not (entry.from_event and entry.status == status):
                entry.status, entry.since, entry.lower_bound = status, self.clock(), False
            entry.seq, entry.from_event = seq, False
        return entry

    def event(self, pane_id, status):
        """A `pane.agent_status_changed` event: the exact moment of a change. The poll that
        later sees its new `state_change_seq` keeps this time instead of its own."""
        entry = self.entries.get(pane_id)
        if entry is not None and status != entry.status:
            entry.status, entry.since, entry.lower_bound, entry.from_event = status, self.clock(), False, True

    def _first(self, seq, status, summary):
        """A pane seen for the first time starts at its last conversation line (nothing
        else is written while it sits idle; spike 0-19), else now as a lower bound."""
        last = summary.last_activity if summary is not None else None
        if last is not None:
            return Entry(seq, status, last, False)
        return Entry(seq, status, self.clock(), True)


def text(entry, now):
    """The idle column: `12m`, `3h05m`, `2d`, with `≥` when only a lower bound is known;
    `—` while Claude works."""
    if entry is None:
        return ""
    if entry.status == "working":
        return "—"
    age = display.age((now - entry.since).total_seconds())
    return "≥" + age if entry.lower_bound else age
