"""Claude's own background sessions (Claude Code 2.1.28x): `claude --bg`, `/bg`, and
`claude attach <id>`, which shows one in a pane while it runs outside it. `/exit` there
does not stop it."""

from collections import namedtuple

from . import inventory

Seen = namedtuple("Seen", "process argv env command entries")


def look(rt, pane_id):
    """The Claude process in `pane_id` (its argv, account variables, the `claude` to run for
    it) and Claude's session list, read with that `claude` and those variables."""
    process = inventory.claude_process(rt.herdr.process_info(pane_id)) or {}
    argv = inventory.argv_of(process, rt.system) if process else []
    env = inventory.account_env(process, rt.system, rt.settings)
    command = inventory.claude_executable(argv[0] if argv else None, rt.settings, rt.system, rt.environ)
    return Seen(process, argv, env, command, rt.system.claude_agents(command, env))


NOT_RUNNING = ("this pane attaches to Claude's background session %s, which Claude does not list as "
               "running; look at the pane (g)")


def attached_to(argv):
    """The id a `claude attach <id>` client shows, else None."""
    return argv[2] if len(argv) > 2 and argv[1] == "attach" else None


def running_background(entries, session_id, short_id=None):
    """Claude's entry for `session_id` (or the one whose short id is `short_id`, which a
    `claude attach` client names) when it runs in the background, from its session list
    (`claude agents --json`: `id` is the short id `claude stop` takes), else None. Only a live
    worker counts (it has a `pid`): a stopped one stays listed and can be resumed as a
    Claude of its own."""
    for entry in entries or []:
        mine = entry.get("id") == short_id if short_id else entry.get("sessionId") == session_id
        if entry.get("kind") == "background" and mine and entry.get("pid"):
            return dict(entry, id=entry.get("id") or session_id[:8])
    return None


def not_idle(entry, where=" in the background"):
    """Why the session of Claude's `entry` is not parked now, or None when it is idle. Herdr's
    status for a pane may be another session's (seen on the Mac and in a container);
    Claude's list says `busy`, or `waiting` with what for (`permission prompt`)."""
    if entry.get("status") == "idle":
        return None
    if entry.get("waitingFor"):
        return "Claude waits for a %s%s; answer it first (g)" % (entry["waitingFor"], where)
    return "Claude is %s%s; only idle sessions park" % (entry.get("status") or "unknown", where)


def why_not_stop(entry, title):
    """Why the background session `entry` is not stopped from a pane titled `title`, or None.
    A view titles its pane after the session it shows, while Herdr may keep the id of one it
    showed before: another name there means the id is stale."""
    if entry.get("name") and title != entry["name"]:
        return ('the pane shows "%s", not "%s" that Herdr names for it; look at the pane (g)'
                % (title or "", entry["name"]))
    return not_idle(entry)


def own_session(seen, pane):
    """(the session the pane's Claude runs, a remark, Claude's entry for it or None). Claude's
    list gives its interactive sessions by `pid`, which beats Herdr's id: the hooks of
    background workers started from a pane report to that pane for the daemon's lifetime
    (seen in a container, where Herdr named another session). Herdr's id otherwise."""
    pid = seen.process.get("pid")
    for entry in seen.entries or []:
        if entry.get("kind") == "interactive" and pid and entry.get("pid") == pid and entry.get("sessionId"):
            said = entry["sessionId"]
            remark = "" if said == pane.session_id else "Herdr named %s; Claude says %s" % (
                (pane.session_id or "none")[:8], said[:8])
            return said, remark, entry
    return pane.session_id, "", None
