# Agent parking

A [Herdr](https://herdr.dev) plugin that parks idle Claude Code sessions and brings
them back in place.

An idle `claude` process keeps 200–370 MB and keeps running the version it started
with. Exiting it frees the memory and lets the next start pick up the current
version, but then you have to note the session somewhere to find it again. Agent
parking does that bookkeeping: it records how to resume each session before it
exits, keeps the pane (labelled `💤 <title>`), and resumes the same session in the
same pane with one key, with a note you left when you parked it.

```
 Agent parking · 3 claude · 1.1G
 ────────────────────────────────────────────────────────────────────────────────
   place          name            status   idle   ctx           rss   ver
 ▶ w8/t3/p36 web  api gateway     idle     ≥1h12m 37k 18%       205M  2.1.283
   w8/t4/p3A      invoice import  done     3h05m  compacted 2h  192M  2.1.281 old
   wD/t2/p2T 💤   color notes     parked   2d     compacted 2d  —
     ↳ "stopped before pasting the table into the wiki"
 ────────────────────────────────────────────────────────────────────────────────
 s park  c compact  C compact+park  r resume  R swap  g go  S idle≥60m  n note  …
```

## Requirements

- Herdr 0.9.1 or later, on macOS or Linux, with `python3` 3.9 or later on the path
  (standard library only).
- Claude Code with Herdr's Claude integration: `herdr integration status` shows
  `claude: current`. The plugin reads the session id Herdr detects in each pane.
- Codex is not handled: its sessions live in a shared daemon, so exiting the TUI frees
  little and does not stop the work.

## Install

```sh
herdr plugin install haretoke/herdr-agent-parking
```

or, from a clone, `herdr plugin link /path/to/herdr-agent-parking`.

The plugin adds two actions: **Open agent parking** (the dashboard over the active
pane) and **Open agent parking in a tab** (to keep it open; idle times are tracked
only while a dashboard runs). There is one dashboard at a time: opening it again moves
an overlay to where you are, and a dashboard kept in a tab is focused instead. A plugin cannot bind keys itself; add one to Herdr's
`config.toml`:

```toml
[[keys.command]]
key = "prefix+a"   # prefix+p is previous_tab by default
type = "plugin_action"
command = "haretoke.agent-parking.open"
description = "agent parking"
```

## Keys

| Key | What it does |
|---|---|
| `s` | Park: record how to resume, send `/exit`, keep the pane labelled `💤 …`. Asks for a note first |
| `r` | Resume a parked session in its pane (`claude --resume <id>` with the flags it had). A closed pane is recreated where it was |
| `R` | Swap: park and resume at once, to restart on the current `claude` |
| `c` | Compact: Claude prepares (`/prepare-compact`), you check its report and the focus, then `/compact <focus>` |
| `C` | Compact, then park (the note is asked first) |
| `S` | Park every session idle for at least a threshold (60 minutes by default, editable) |
| `n` / `x` | Edit a parked session's note / forget its record (the transcript is never touched) |
| `g` | Go to the pane and close the dashboard |
| `/`, `i`, `?`, `q` | Filter, detail line, key help, close |

Only `idle` and `done` sessions with an empty input box are parked or compacted, and
only once they have a conversation: a Claude that was never prompted has nothing to
resume, so exit it instead.
Parking ends the process: background tasks, running subagents and MCP server state
do not come back.

From a shell inside Herdr the same procedures run without the dashboard:
`python3 -m agent_parking park <pane> [--note TEXT]`, `compact <pane> [--focus TEXT]`
(prepares, prints the report, then compacts with the proposed focus),
`resume <uuid> [--new-workspace]`, and `list` (the rows as JSON), run from the plugin
directory.

## The prepare-compact skill

`c` and `C` send `/prepare-compact`: a Claude Code skill that saves what lives only
in the conversation, reports uncommitted and unpushed work and what it cleaned up,
and ends with a `<compact-focus>…</compact-focus>` line the dashboard offers as the
`/compact` focus. Copy it into your skills:

```sh
cp -R skills/prepare-compact ~/.claude/skills/
```

Without it Claude answers `Unknown command`, and the dashboard sends a built-in
request with the same steps instead (`prepare_prompt` in the settings replaces it).
The skill also works on its own: say "I want to compact" and it prepares, then hands
you a ready `/compact` line.

### Compact Instructions

For what every summary must keep in a project, add a section to its `CLAUDE.md`:

```markdown
## Compact Instructions

Keep the open TODO list, the port map and the names of the branches in flight.
```

Claude Code applies it to a manual `/compact`, which is what the dashboard sends. In
our test it did not reach an automatic compaction, so do not rely on it there.

## Settings

`config.json` in the plugin's config directory (`herdr plugin config-dir
haretoke.agent-parking`). Every key is optional:

| Key | Default | |
|---|---|---|
| `on_park` | `"keep"` | `"close"` closes the pane after the park (never the last pane of a tab); `r` recreates it |
| `parked_label_format` | `"💤 {title}"` | The label of a parked pane |
| `bulk_idle_minutes` | `60` | `S`'s starting threshold |
| `send_note_as_prompt` | `false` | Send the note as the first prompt after a resume (once Claude is idle) |
| `context_window_by_model` | `{}` | Model id prefix → window size, for the ctx percentage (`{"claude-haiku-4-5": 200000}`) |
| `prepare_command` / `prepare_prompt` | `"/prepare-compact"` / none | What `c` sends to prepare |
| `poll_seconds`, `exit_timeout_seconds`, `start_timeout_ms`, `prepare_timeout_seconds`, `compact_timeout_seconds` | 2, 20, 30000, 600, 300 | Waits |
| `claude_command`, `claude_config_dir`, `records_dir`, `resumed_keep_days` | | Where things are |

The ctx percentage needs the window size. Besides the setting, a statusline can
write it for each session: Claude's statusline input has `session_id` and
`context_window.context_window_size`; merge `{session_id: size}` into
`context-windows.json` in the plugin's state directory.

## Limits

- Idle time is tracked only while a dashboard runs; before that it is taken from the
  last line of the transcript, or shown as a lower bound (`≥3m`).
- A dashboard open during a Herdr server restart comes back as a plain shell labelled
  `Agent parking`; close it.
- Records live in the plugin's state directory, per Herdr server: in a container they
  stay with the container.

## License

MIT
