"""The launch flags a resume replays: a parked Claude's argv minus what picks or names
the session, and minus an initial prompt that a resume would send again. Pure functions."""

from collections import namedtuple

ResumeFlags = namedtuple("ResumeFlags", "flags dropped")

# How many values each flag of `claude --help` (2.1.283) takes: "required" (one),
# "optional" (one unless the next token is a flag), "variadic" (until the next flag).
# Flags missing here are switches.
ARITY = {
    "--add-dir": "variadic",
    "--agent": "required",
    "--agents": "required",
    "--allowedTools": "variadic", "--allowed-tools": "variadic",
    "--append-system-prompt": "required",
    "--append-system-prompt-file": "required",
    "--autocompact": "required",
    "--betas": "variadic",
    "--client-data-url": "required",
    "--cloud": "optional",
    "--debug": "optional", "-d": "optional",
    "--debug-file": "required",
    "--disallowedTools": "variadic", "--disallowed-tools": "variadic",
    "--effort": "required",
    "--environment": "required",
    "--fallback-model": "required",
    "--file": "variadic",
    "--from-pr": "optional",
    "--input-format": "required",
    "--json-schema": "required",
    "--max-budget-usd": "required",
    "--mcp-config": "variadic",
    "--model": "required",
    "--name": "required", "-n": "required",
    "--output-format": "required",
    "--permission-mode": "required",
    "--permission-prompts": "required",
    "--plugin-dir": "required",
    "--plugin-url": "required",
    "--prompt-suggestions": "optional",
    "--remote-control": "optional",
    "--remote-control-session-name-prefix": "required",
    "--resume": "optional", "-r": "optional",
    "--session-id": "required",
    "--setting-sources": "required",
    "--settings": "required",
    "--system-prompt": "required",
    "--system-prompt-snapshot": "required",
    "--teleport": "optional",
    "--tools": "variadic",
    "--worktree": "optional", "-w": "optional",
}

# Flags that pick or name the session; the resume supplies `--resume <uuid>` itself.
SESSION_FLAGS = {"--resume", "-r", "--continue", "-c", "--session-id", "--name", "-n",
                 "--fork-session", "--from-pr", "--teleport"}


def _is_flag(token):
    return token.startswith("-") and token != "-"


def resume_flags(argv):
    """The flags of `argv` (executable first) to pass after `--resume <uuid>`, and the
    tokens left out that are not session flags (an initial prompt, an unknown flag's
    value), for the confirmation box."""
    flags, dropped = [], []
    tokens = list(argv[1:])
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if not _is_flag(token):
            dropped.append(token)
            continue
        name, has_value, _ = token.partition("=")
        group = [token]
        arity = ARITY.get(name)
        if not has_value and arity == "required" and i < len(tokens):
            group.append(tokens[i])
            i += 1
        elif not has_value and arity in ("optional", "variadic"):
            while i < len(tokens) and not _is_flag(tokens[i]):
                group.append(tokens[i])
                i += 1
                if arity == "optional":
                    break
        if name not in SESSION_FLAGS:
            flags.extend(group)
    return ResumeFlags(flags=flags, dropped=dropped)
