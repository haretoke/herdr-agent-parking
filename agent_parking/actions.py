"""What the dashboard's keys do, on the real Herdr and records (the dashboard itself only
decides when; tests give it a fake)."""

from . import park, records


class Actions:
    def __init__(self, rt, tracker):
        self.rt = rt
        self.tracker = tracker

    def focus(self, pane_id):
        """`g`: the overlay does not take an explicit focus back when it closes (spike 0-4)."""
        self.rt.herdr.call("pane.focus", {"pane_id": pane_id})

    def park(self, pane_id, note):
        return park.park(self.rt, pane_id, note)

    def forget(self, session_id):
        records.forget(self.rt.paths.records, session_id)
