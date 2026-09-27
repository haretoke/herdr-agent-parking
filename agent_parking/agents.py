"""Claude's own background sessions (Claude Code 2.1.28x): `claude --bg`, `/bg`, and
`claude attach <id>`, which shows one in a pane while it runs outside it. `/exit` there
does not stop it."""

BACKGROUND = ("this pane shows a session that runs in Claude's background (%s); /exit would leave "
              "it running. `claude stop %s` stops it")


def attached_to(argv):
    """The id a `claude attach <id>` client shows, else None."""
    return argv[2] if len(argv) > 2 and argv[1] == "attach" else None
