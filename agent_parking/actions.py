"""What the dashboard's keys do, on the real Herdr and records (the dashboard itself only
decides when; tests give it a fake)."""

from . import park, records, resume


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

    def set_note(self, session_id, note):
        """`n`: the record as it is now, with the new note (blank means none)."""
        record = records.read(self.rt.paths.records, session_id)
        if record is None:
            return "the record is gone"
        record["note"] = note if note and note.strip() else None
        records.write(self.rt.paths.records, record)
        return None

    def now(self):
        return self.rt.clock()

    def resume(self, session_id, new_workspace):
        return resume.resume(self.rt, session_id, new_workspace=new_workspace)
