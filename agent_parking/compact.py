"""Compacting a Claude from the dashboard: ask it to prepare, read the focus it proposes,
then send `/compact <focus>`.

Outcome kinds: refused, blocked, prepared, prepare_failed, compacted, compact_failed.
"""

from collections import namedtuple

from . import agents, config, herdr_api, park, ready, transcript

Outcome = namedtuple("Outcome", "kind message reply")


def prepare(rt, pane_id):
    """Send the preparation (`prepare_command`, or `prepare_prompt` when set), wait for it,
    and read Claude's reply and proposed focus from the transcript."""
    pane, refusal = ready.check(rt, pane_id, "compact")
    if refusal:
        return Outcome("refused", refusal, None)
    session_id, refusal = _session(rt, pane_id, pane)
    if refusal:
        return Outcome("refused", refusal, None)
    preparation = config.preparation(rt.settings)
    rows = rt.rows_for(session_id)
    for text in (preparation.first, preparation.fallback):
        earlier = transcript.pending_preparation(rows, text) if text else None
        if earlier is not None:
            return Outcome("prepared", "using the earlier preparation (not sent again)", earlier)
    sent, note = preparation.first, ""
    try:
        result = _send_and_wait(rt, pane_id, sent)
    except herdr_api.HerdrError as error:
        # A missing skill is answered locally with "Unknown command" and never starts a
        # turn, so the prompt stalls (spike 0-18).
        if error.code != "agent_prompt_stalled" or UNKNOWN_COMMAND not in rt.herdr.screen(pane_id):
            raise
        if preparation.fallback is None:
            return Outcome("prepare_failed", "Claude answered %s %s" % (UNKNOWN_COMMAND, sent), None)
        sent, note = preparation.fallback, "%s is not installed; sent the built-in request" % sent
        result = _send_and_wait(rt, pane_id, sent)
    if (result.get("agent") or {}).get("agent_status") == "blocked":
        return Outcome("blocked", "Claude stopped at a dialog while preparing; go to the pane (g), "
                                  "answer it, then press c again", None)
    reply = transcript.preparation_reply(rt.rows_for(session_id), sent)
    return Outcome("prepared", note, reply)


def _session(rt, pane_id, pane):
    """(the session the pane's Claude runs, why not to compact it or None): Claude's own list
    beats Herdr's id and status (seen in a container, where Herdr named another session)."""
    own, _, entry = agents.own_session(agents.look(rt, pane_id), pane)
    return own, entry and agents.not_idle(entry, "")


UNKNOWN_COMMAND = "Unknown command:"


def _send_and_wait(rt, pane_id, text):
    # The wait rides on the prompt request, so no status change can slip in between
    # (it may take minutes: the preparation can commit and push).
    seconds = rt.settings["prepare_timeout_seconds"]
    return rt.herdr.call("agent.prompt", {"target": pane_id, "text": text, "wait": {
        "until": ["idle", "done", "blocked"], "timeout_ms": int(seconds * 1000)}},
        timeout=seconds + herdr_api.WAIT_MARGIN_SECONDS)


REPORT_LINES = 8


def confirmation(reply):
    """The lines of the compact confirmation: the end of the preparation report (without
    the focus tag and the ready-to-type command) and the focus, which can be edited."""
    report = [line for line in reply.text.splitlines()
              if line.strip() and not transcript.FOCUS.search(line) and "/compact" not in line]
    focus = reply.focus or "(none, /compact alone)"
    return (["preparation report (end):"] + ["  " + line for line in report[-REPORT_LINES:]] +
            ["focus: " + focus, "Enter to compact, e to edit the focus, Esc to cancel"])


def run(rt, pane_id, focus):
    """Send `/compact <focus>` (one line; `/compact` alone without a focus) and wait for it.
    It is done when a compact boundary newer than the request is in the transcript
    (spike 0-21); otherwise `compact_failed`."""
    pane, refusal = ready.check(rt, pane_id, "compact")
    if refusal:
        return Outcome("refused", refusal, None)
    session_id, refusal = _session(rt, pane_id, pane)
    if refusal:
        return Outcome("refused", refusal, None)
    line = " ".join((focus or "").split())
    sent_at = rt.clock()
    timeout = rt.settings["compact_timeout_seconds"]
    rt.herdr.call("agent.prompt", {"target": pane_id, "text": ("/compact " + line).strip(), "wait": {
        "until": ["idle", "done"], "timeout_ms": int(timeout * 1000)}},
        timeout=timeout + herdr_api.WAIT_MARGIN_SECONDS)
    if transcript.compacted_since(rt.rows_for(session_id), sent_at):
        return Outcome("compacted", "", None)
    return Outcome("compact_failed", "no new compaction in the transcript within %s s" % timeout, None)


def compact_then_park(rt, pane_id, focus, note):
    """`C`: compact with `focus`, then park with `note` (asked before anything started).
    A compaction that fails does not park. Returns (compact Outcome, park Outcome or None)."""
    compacted = run(rt, pane_id, focus)
    if compacted.kind != "compacted":
        return compacted, None
    return compacted, park.park(rt, pane_id, note)
