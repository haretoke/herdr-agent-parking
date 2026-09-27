"""Claude's own background sessions (Claude Code 2.1.28x): `claude --bg`, `/bg`, and
`claude attach <id>`, which shows one in a pane while it runs outside it. `/exit` there
does not stop it."""

BACKGROUND = ("this pane shows a session that runs in Claude's background (%s); /exit would leave "
              "it running. `claude stop %s` stops it")
STILL_RUNNING = ("%s still runs in Claude's background as %s: `claude attach %s` opens it in a pane; "
                 "x (void) forgets this record")


def attached_to(argv):
    """The id a `claude attach <id>` client shows, else None."""
    return argv[2] if len(argv) > 2 and argv[1] == "attach" else None


def running_background(entries, session_id):
    """Claude's entry for `session_id` when it runs in the background, from its session list
    (`claude agents --json`: `id` is the short id `claude stop` takes), else None. Only a live
    worker counts (it has a `pid`): a stopped one stays listed and can be resumed as a
    Claude of its own."""
    for entry in entries or []:
        if entry.get("kind") == "background" and entry.get("sessionId") == session_id and entry.get("pid"):
            return dict(entry, id=entry.get("id") or session_id[:8])
    return None


def not_idle(entry):
    """Why a background session is not stopped now, or None when it is idle. Herdr's status
    for a pane showing one is not its own (seen on the Mac); Claude's list says `busy`, or
    `waiting` with what for (`permission prompt`)."""
    if entry.get("status") == "idle":
        return None
    if entry.get("waitingFor"):
        return "Claude waits for a %s in the background; answer it first (g)" % entry["waitingFor"]
    return "Claude is %s in the background; only idle sessions park" % (entry.get("status") or "unknown")


def why_not_stop(entry, title):
    """Why the background session `entry` is not stopped from a pane titled `title`, or None.
    A view titles its pane after the session it shows, while Herdr may keep the id of one it
    showed before: another name there means the id is stale."""
    if entry.get("name") and title != entry["name"]:
        return ('the pane shows "%s", not "%s" that Herdr names for it; look at the pane (g)'
                % (title or "", entry["name"]))
    return not_idle(entry)
