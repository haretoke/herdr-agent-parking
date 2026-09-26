"""The launch flags a resume replays: a parked Claude's argv minus what picks or names
the session. Pure functions."""

from collections import namedtuple

ResumeFlags = namedtuple("ResumeFlags", "flags dropped")

# Flags that pick or name the session; the resume supplies `--resume <uuid>` itself.
# Value: "none" (a switch), "required" (one value) or "optional" (a value unless the
# next token is a flag).
SESSION_FLAGS = {
    "--resume": "optional", "-r": "optional",
    "--continue": "none", "-c": "none",
    "--session-id": "required",
    "--name": "required", "-n": "required",
    "--fork-session": "none",
}


def resume_flags(argv):
    """The flags of `argv` (executable first) to pass after `--resume <uuid>`."""
    flags = []
    tokens = list(argv[1:])
    i = 0
    while i < len(tokens):
        token = tokens[i]
        name, has_value, _ = token.partition("=")
        arity = SESSION_FLAGS.get(name)
        i += 1
        if arity is None:
            flags.append(token)
        elif not has_value and (arity == "required" or (
                arity == "optional" and i < len(tokens) and not tokens[i].startswith("-"))):
            i += 1
    return ResumeFlags(flags=flags, dropped=[])
