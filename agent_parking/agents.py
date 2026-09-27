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
    """The short id under which Claude runs `session_id` in the background, from its session
    list (`claude agents --json`), else None. Only a live worker counts (it has a `pid`): a
    stopped one stays listed and can be resumed as a Claude of its own."""
    for entry in entries or []:
        if entry.get("kind") == "background" and entry.get("sessionId") == session_id and entry.get("pid"):
            return entry.get("id") or session_id[:8]
    return None
