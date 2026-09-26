# herdr-agent-parking design

A public plugin for Herdr 0.9.1. It lists the Claude Code panes running on this
Herdr server, stops ("parks") sessions that are waiting, and later resumes them in
the same pane. It also compacts a session's context before parking. The shape
follows `haretoke.image-viewer` (herdr-image-viewer).

Status: design before implementation (decisions approved 2026-09-27). What is
still unverified is listed under "Open items" and appears as spikes in `plan.md`.

## Decisions

- Plugin id `haretoke.agent-parking`, public GitHub repository
  `haretoke/herdr-agent-parking`, Python package `agent_parking`, MIT license.
  The name is agent-neutral: adding Codex later does not rename anything. v1 manages
  Claude Code only.
- The dashboard opens as an `overlay` by default; the `open-tab` action opens it as
  a tab for people who keep it open.
- Documents (README, DESIGN.md, plan.md) are in English.
- `on_park` defaults to `keep`: the parked pane stays as an empty shell with a
  `💤 {title}` label. `close` is the alternative.
- Defaults approved as proposed: label format `💤 {title}` (configurable); the note is
  also echoed into the pane's scrollback before a resume; `send_note_as_prompt` stays a
  setting, default `false`; `records_dir` defaults to the plugin state directory
  (lost on a container rebuild, configurable); resumed records are kept 30 days and
  `x` asks for confirmation; `S` defaults to 60 minutes and includes rows whose idle
  time is only a lower bound (`≥`); Codex panes are not listed, only counted in the
  footer; `R` (swap) asks for confirmation when the running version equals the
  current one; RSS is the sum over the foreground process group, with the Claude-only
  value kept in the JSON output; `g` sends `pane.focus` and exits, in every placement
  (spike 0-4: the overlay does not take an explicit focus back).
- The resume key is always the session UUID. Names are never used to resume.
- The dashboard needs no new Claude hook: it reads `agent_session` and the launch
  argv before it sends `/exit`. Recording sessions that were exited by hand is an
  optional extension.
- A `ctx` column shows context usage and whether the session is compacted, read from
  the transcript. `c` compacts, `C` compacts and parks. Compaction is prepared by a
  `/prepare-compact` skill shipped in this repository (or a built-in prompt).
- Whether a pane's foreground is only the shell is decided by `pid == shell_pid`,
  never by the process name (both `-zsh` and `zsh` were seen on real devices).

## Purpose

- Stop Claude Code processes that are waiting and get their memory back (measured on a
  Mac: 200-370 MB per process, about 2.1 GB for 9 processes), and start them again on
  a newer CLI.
- Leave a trace nobody has to write down by hand: the plugin's record plus the label
  on the pane that stays behind.
- Resume in the original pane so the workspace / tab / cwd arrangement is kept.
- Shrink a session's context with `/compact` after a preparation step, on demand or
  right before parking.

## Out of scope

- **Codex** (0.157.1). It uses a shared, self-updating daemon; `/exit` only disconnects
  ("Any running work continues"). `codex resume <name>` fails through the daemon while
  a UUID resumes. Only listed as a future extension.
- Agents other than Claude Code (pi, opencode, ... as detected by Herdr). Not listed.
- Cross-server views (`--machine`). In a thin-client setup the plugin runs on the
  server, so there is one dashboard per server.
- Managing Claude session names (`/rename`). `/clear` mints a new UUID but carries the
  `session_title` over, so two sessions share a name and `claude --resume <name>`
  opens the picker (verified on a real device). The resume key is the UUID.
- Restarting or updating the Herdr server itself.

## Terms

| Term | Meaning |
|---|---|
| Claude pane | A pane whose `agent == "claude"` in `pane list`; `agent_session.value` is the session UUID |
| park | Send `/exit` to an idle/done Claude pane, write a record, and keep the pane with a marked label (or close it with `on_park = close`) |
| record | The JSON for a parked session, keyed by the session UUID |
| resume | Start `claude --resume <UUID>` in the original pane from the record |
| recreate | When the original pane is gone, create a pane from the record's tab / cwd and resume there |
| swap | Park and resume right away, so the session comes back on the current `claude` executable |
| compact | Run the preparation step, then send `/compact <focus>` to the session |
| idle time | Time since the pane's `agent_status` last changed (tracked by the plugin) |
| ctx | Context usage of the session: tokens, percentage when the window size is known, or `compacted <age>` |
| dashboard | The plugin's `[[panes]]` entrypoint: the list and the operations as a TUI |

## Functional requirements

### The list (dashboard)

Every Claude pane on this server, with these columns:

| Column | Source |
|---|---|
| place | `workspace_id` / `tab_id` / `pane_id` (`pane list`), the workspace label (`workspace list`), the tab label (`tab list`), the pane `label` (set with `pane rename`) |
| name | `terminal_title_stripped` (Claude writes the `-n` / `/rename` / generated title to the terminal title). For a parked session, the record's `title` |
| cwd | `pane.cwd` (the record's `cwd` when there is a record) |
| status | `agent_status` (working / idle / done / blocked / unknown); `parked` for a parked session |
| idle | The plugin's tracking (below). Time that began before tracking started is shown as a lower bound with `≥` |
| ctx | From the transcript (below): `37k 18%`, `37k`, or `compacted 2h`. Empty when the transcript cannot be read |
| rss | `VmRSS` from `/proc/<pid>/status` on Linux, else `ps -o rss= -p` (both KiB, spike 0-9), over every `pid` in `pane process-info`'s `foreground_processes`, summed (MCP servers and `caffeinate` sit in the same foreground group as Claude; parking frees the whole group). The Claude-only value is kept in the JSON output. Empty for parked sessions |
| ver | The running version: on Linux the basename of `readlink /proc/<pid>/exe`, on macOS `process-info`'s `name` (the basename of `~/.local/share/claude/versions/<v>`). The current version: the `realpath` of the running `argv[0]` when it is a path (macOS), else of `claude_command` on `PATH`, else of `~/.local/bin/claude` (the plugin runs in the Herdr server's environment). `old` when they differ; no badge when either is unknown. On Linux Herdr 0.9.1 gives the Claude process no `argv`, so argv comes from `/proc/<pid>/cmdline` (spike 0-10) |
| parked | Records show 💤, the park time and the first line of the note |

- The dashboard's own pane and non-Claude panes are not listed. The footer shows the
  count, the total Claude RSS, and the number of Codex panes ("codex: n, not managed").
- A record whose pane is gone (closed by hand, or lost with a rebuilt container) is
  listed at the end as "(no pane)". A server restart alone keeps pane IDs (spike 0-1).
- **Reconciliation**: every refresh matches records against panes. After `/exit`,
  Claude prints `Resume this session with: claude --resume ...` in the pane, so
  people resume by hand, and sometimes in another pane. The match runs against the
  `agent_session.value` of **every** Claude pane, not only the record's `pane_id`.
  If the record's UUID is running anywhere, the record becomes `resumed` and the
  original pane's label is restored; if it was found in another pane, `pane_id` is
  moved and the old ID goes to `pane_id_history`. If the record's pane hosts a
  different UUID, the row says "another session is running here" and the record
  stays (`r` refuses, `x` forgets). Retrying `resume_pending` is part of the same
  reconciliation.

### Operations

| Key | Operation | Condition |
|---|---|---|
| `j` / `k` / `↓` / `↑` | Move the selection | |
| `s` | Park | `agent_status` is `idle` or `done` and the input box is empty; `working` / `blocked` / `unknown` are refused with a reason |
| `c` | Compact | Same as park |
| `C` | Compact, then park (the note is asked first) | Same as park |
| `r` | Resume | A row with a record. Recreate when the pane is gone |
| `R` | Swap (park → resume) | Same as park. Asks for confirmation when the running version equals the current one |
| `g` | Go to the pane (socket `pane.focus {pane_id}`) and close the dashboard | A row with a pane. Works in every placement: the overlay does not take an explicit focus back when it closes (spike 0-4) |
| `S` | Park every session idle for at least a threshold | Lists idle/done rows at or above the threshold, including `≥` rows, confirms, then parks in order. The threshold is the only condition; ctx is not |
| `n` | Edit the note | A row with a record |
| `x` | Forget the record | A row with a record. Asks for confirmation. Never touches the transcript |
| `/` | Filter (name, cwd, label) | |
| `?` | Key help | |
| `q` | Close | |

Park, swap and `C` ask for a note (Enter on an empty line means no note). Bulk park
attaches one note to all (may be empty).

### The note

- Free text, several lines allowed, stored in the record.
- The list shows the first line.
- Before a resume, the dashboard shows the full note in the confirmation. Right
  before the resume it is also printed into the pane's scrollback (`pane.send_input` of
  a `printf` command). With Claude in full-screen TUI mode it disappears at once, so the
  confirmation is the primary display and the scrollback is secondary.
- **Not sent as the first prompt after the resume (default).** The comparison:

| | send | do not send (default) |
|---|---|---|
| for | Claude knows at once what was going on; nobody retypes it | Nothing starts on its own; the "next step" in the note can be adjusted after looking at the situation; no tokens spent |
| against | The note is read as an instruction, `working` starts and the prompt is taken; a trust or "Resume from summary" dialog would receive the text | A person reads and retypes |

  The setting `send_note_as_prompt` exists, default `false`. Even when `true`, the
  note is sent with `agent prompt` only after `agent_status` becomes `idle` after the
  resume (never on top of a dialog).

### The ctx column

Facts verified on real devices and in the documentation:

- Claude's statusline `used_percentage` is
  `(input_tokens + cache_creation_input_tokens + cache_read_input_tokens) / context_window_size`,
  truncated (measured 36,890 / 200,000 → 18). Output tokens are not part of it.
- The numerator can be taken exactly from the transcript: the sum of those three
  fields in the last `assistant` line that has `message.usage`, after the last
  `compact_boundary` line.
- The denominator (the window size) is not in the transcript. The documentation says
  "200000 by default, 1000000 for extended-context models". Haiku is 200k; an Opus 5.5
  session was seen using 279k (so 1M).
- Display: the token count is always shown (`37k`). The percentage only when the
  denominator is known: (a) the `context_window_by_model` setting (a table from model
  id prefix to tokens; the model id is `message.model` on the same assistant line),
  or (b) the optional statusline integration: the statusline's stdin JSON carries
  `session_id` and `context_window.context_window_size`, so a user can add one line to
  their statusline that writes `{session_id: context_window_size}` into the plugin's
  state directory (`context-windows.json`; the README explains it, it is optional).
  With neither, only the token count.
- **Compacted**: the last `compact_boundary` line (`type: "system"`,
  `subtype: "compact_boundary"`, with `timestamp` and
  `compactMetadata {trigger, preTokens, postTokens}`) exists and no `assistant` line
  with `message.usage` follows it. The compaction summary is stored after the boundary
  as a `type: "user"` line with `isCompactSummary: true`, so "no user line after the
  boundary" must not be the condition (verified). On the statusline side,
  `current_usage` and `used_percentage` are null right after a compaction and fill in
  on the next API call (verified on a device and in the docs).
- A compacted session shows `compacted <age>` (`compacted 2h`). The age is exact
  because it comes from the boundary line's `timestamp`, even for time before the
  dashboard was opened.
- Finding the transcript: glob `<claude_config_dir>/projects/*/<uuid>.jsonl` (the
  directory slug rule is not reimplemented). `claude_config_dir` is configurable,
  default `$CLAUDE_CONFIG_DIR` or `~/.claude`. Read from the tail, cached by mtime and
  size (the dashboard looks at many sessions every 2 seconds and transcripts get
  large). When it cannot be read, ctx is empty.
- Parked sessions still have a transcript, so their ctx is shown too.

### Compact (`c`) and compact-then-park (`C`)

Conditions: `idle` or `done`, and the input box is empty (the same check as park).

1. Send the preparation command with `agent prompt`: `prepare_command` (default
   `/prepare-compact`). For environments without the skill, the setting
   `prepare_prompt` sends the built-in request text instead. When the skill is missing,
   Claude answers `Unknown command: /prepare-compact` locally and `agent prompt`
   returns `agent_prompt_stalled` (spike 0-18); the flow then sends the built-in text
   and notes it in the confirmation box.
2. `agent wait --until idle` with a long timeout (`prepare_timeout_seconds`, default
   600), because the preparation may commit and push.
3. Find the line the plugin sent in the transcript and take the focus tag from the
   assistant text after it (`<compact-focus>...</compact-focus>`).
4. Show a confirmation with a summary of the preparation report and the focus; the
   focus can be edited. Without a tag, the focus is shown empty and can be typed.
5. `agent prompt <P> "/compact <focus>"`: the focus is one line (newlines become
   spaces); an empty focus sends `/compact` alone.
6. `agent prompt ... --wait` returns once the compaction is over, and the new
   `compact_boundary` line is already written then (spike 0-21, 16 s for a small
   session). The flow confirms that the boundary count grew; ctx turns into
   `compacted`. `C` then continues with the park procedure. The preparation reply is
   also in the transcript as soon as its wait returns (spike 0-22).

If the agent becomes `blocked` during the preparation (a permission dialog or a
question), the flow stops and the dashboard says to go to the pane. Pressing `c`
again resumes from step 3 when a focus tag is already there.

### The park procedure

1. `pane get <P>`: `agent == "claude"`, `agent_status ∈ {idle, done}`, and
   `agent_session.value` is a UUID. Otherwise refuse.
   Then `agent read <P> --format ansi` to make sure Claude's input box is empty: with
   a half-typed line, `agent prompt "/exit"` appends `/exit` and submits both as a
   prompt (spike 0-13). The box is the last `❯` line between two `─` rules; it is empty
   when nothing follows `❯ ` except dim (`ESC[2m`) placeholder text. If not empty,
   refuse with "a draft is in the input box" (the person clears it with `g` + Ctrl+C).
2. `pane process-info --pane <P>`: the Claude process is the foreground group leader
   (`pid == foreground_process_group_id`); take its `pid` and `cwd`, its `argv` (from
   `/proc/<pid>/cmdline` when Herdr gives none, as on Linux) and its version (see the
   `ver` column). Also `layout.export` of the tab to store, in the record's
   `layout_hint`, the pane's sibling in the split tree (a pane id, or `null` when the
   sibling is a subtree), whether the pane was the `first` or `second` child, the
   split direction and ratio (used by recreate; stored regardless of `on_park`).
3. RSS from `/proc/<pid>/status` or `ps -o rss= -p` (display only; continue on failure).
4. Ask for the note.
5. **Before `/exit`**, write the record (atomic rename, 0600), `status = "parking"`.
6. `agent prompt <P> "/exit"`.
7. Poll `pane get <P>` up to `exit_timeout_seconds` (default 20) until `agent`
   disappears (the shell is back). Measured: about 4 seconds.
8. Then follow `on_park` ("Parked panes" below).
   - `keep` (default): `pane rename <P> "💤 <name>"` (format `parked_label_format`).
     The previous `label` goes to the record's `label_before`.
   - `close`: check that the foreground is only the shell (`pid == shell_pid`), then
     `pane close <P>`. The last pane of a tab is not closed: it is treated as `keep`
     with a reason (the tab is never closed).
   The record becomes `status = "parked"`; the treatment actually applied is stored in
   `parked_mode`.
9. On timeout the record becomes `status = "park_failed"` with the reason shown. The
   pane is left alone for a person to look at.

The key point: `agent_session` becomes None once Claude exits (verified), so it must
be read before step 6.

### Parked panes (`on_park`, default `keep`)

- **`keep` (default)**: the pane stays as an empty shell with the `💤 <name>` label. Its
  position in the layout does not change and the trace is visible. Resume happens in
  the same pane.
- **`close`**: the pane is closed once the shell is back. The trace is only the plugin's
  record; resume goes through "recreate" from the dashboard. No empty shells pile up,
  but the original position is only approximated through `layout_hint`.
- Either way, resume is `r` in the dashboard. With `keep`, a pane closed by a person
  makes the next `r` a recreate.

### The resume procedure

1. Read the record: `status ∈ {parked, park_failed, resume_failed}`.
2. Check the pane exists (`pane get <P>`); if not, recreate (records with
   `parked_mode = "close"` always go there).
3. Check the pane is free: `process-info`'s `foreground_processes` contains only the
   shell (`pid == shell_pid`). At a shell prompt the list is not empty, it holds the
   shell itself (measured as `-zsh` on one device and `zsh` on another, hence the pid
   check). Anything else running: refuse with a reason.
4. Show the note in the confirmation; Enter continues.
5. `pane.send_input <P>` of `printf '%s\n' '💤 <note>'` + Enter (secondary display;
   continue on failure).
6. `agent start <name> --kind claude --pane <P> --timeout <start_timeout_ms> -- --resume <UUID> <flags>`.
   `<flags>` is the record's `argv` minus the executable and minus `--resume` / `-r` /
   `--continue` / `-c` / `--session-id` / `--name` / `-n` / `--fork-session` /
   `--from-pr` / `--teleport` with their values. An initial prompt given as a positional
   argument (`claude "fix the bug"`) is left out too, because a resume would send it
   again; so is the value of a flag the plugin does not know. Flag arities follow
   `claude --help`. What was left out is shown in the confirmation box. `<name>` is made
   by the plugin (`parking-<first 8 of the UUID>`,
   `[a-z][a-z0-9_-]{0,31}`).
7. On success, `pane get <P>` must show `agent_session.value == UUID`; otherwise warn
   (a different session came up).
8. `pane rename <P> --clear`, or restore `label_before` when there was one.
9. The record becomes `status = "resumed"` and moves to `resumed/` (kept 30 days,
   configurable).
10. With `send_note_as_prompt = true`: `agent wait <P> --until idle --timeout ...`,
    then `agent prompt <P> "<note>"`.
11. When `agent start` returns `agent_not_ready` (a trust dialog, for example), the
    record becomes `status = "resume_pending"` and the dashboard says "answer in the
    pane, then press r again". The label is not restored. The next `r` retries from
    step 3 (when a matching Claude is already running, only steps 7 onwards).

`claude --resume <UUID>` finds sessions of other directories too, but the resume
starts in the record's `cwd`: when the pane's cwd differs, `pane.send_input <P>` of
`cd <cwd>` + Enter first, quoted with `shlex.quote`.

### The recreate procedure

1. If `layout_hint` names a sibling pane that still exists in the same tab, split it
   in the recorded direction: `pane split <sibling> --direction <dir> --cwd <cwd>
   --no-focus`. When the parked pane was the `first` child, swap the new pane into the
   first place (`pane.swap {source_pane_id: <new>, target_pane_id: <sibling>}`). Then
   set the recorded ratio on that split (`layout.set_split_ratio`, `path` = booleans,
   `true` for `second`). This restores the exact position and size (spike 0-15:
   identical rects). When the sibling was a subtree (`null`), or is gone, the position
   cannot be restored with right/down splits: split any pane of the tab to the right
   (`pane split <pane> --direction right --cwd <cwd> --no-focus`), an approximation.
   `layout.apply` is not used: it rebuilds the whole tab and kills its live panes.
2. Without the tab but with an existing `workspace_id`:
   `tab create --workspace <W> --cwd <cwd> --label <tab_label> --no-focus`.
3. Without the workspace, after confirmation:
   `workspace create --cwd <cwd> --label <workspace_label> --no-focus`.
4. Without the `cwd` on disk: stop with a reason (a person picks the place).
5. Write the new pane ID into the record (the old one goes to `pane_id_history`), then
   continue at step 5 of the resume procedure.

### Idle time tracking

Herdr does not report when a status changed: `pane get` / `agent get` carry no time,
`agent get`'s `state_change_seq` is a counter, and the `pane.agent_status_changed`
event has no time either. So the plugin tracks it:

- While the dashboard runs, `observed.json` holds `{pane_id: {seq, status, since}}`.
  Every `poll_seconds` (default 2) it reads `agent list` and sets `since` to now for
  rows whose `state_change_seq` changed. In parallel it holds one `events.subscribe`
  connection with `pane.agent_detected` (no pane: every Claude arriving or leaving,
  `released: true` on exit) and one `pane.agent_status_changed` per Claude pane (that
  type requires a `pane_id`), and reopens it when the set of Claude panes changes
  (spike 0-6). When the connection drops, polling alone continues.
- A row seen for the first time takes `since` from its transcript: the `timestamp` of
  the last `user` / `assistant` line that is not `isMeta` (nothing else is appended
  while a session sits idle; spike 0-19). Only without a readable transcript does it
  get `since = now` and `lower_bound = true`, shown as `≥ 3m`. From the next status
  change on, the dashboard's own tracking takes over.
- Nothing is tracked while the dashboard is closed. People who want continuous
  tracking keep it open in the tab placement. Herdr 0.9.1 plugins have no resident or
  scheduled mechanism (`[[startup]]` runs once and exits, `[[events]]` starts a
  command per event).

### Sessions exited by hand (optional extension, not the main flow)

An `/exit` typed without the dashboard leaves no `agent_session` and no record. v1
does not handle it (the `claude --resume` picker is the way back). Candidates:

- An `[[events]] on = "pane.agent_status_changed"` hook that writes a record if
  `agent_session` is still readable at that moment. Unverified (spike) and unlikely,
  since the value is cleared on process exit. `pane.exited` appears to mean the root
  shell exited, not the foreground child.
- While the dashboard is open, keep `agent_session.value` in `observed.json` and turn
  rows whose Claude disappeared into "exited by hand" records.
- A Claude `SessionStart` hook that writes pane → UUID. It needs devcon-herdr's
  distribution and goes beyond a public plugin, so it stays optional.

## Non-functional requirements

- Python 3.9 or later, standard library only (tests run under `/usr/bin/python3` 3.9
  and `python3` 3.12). 3.9 has no TOML reader, so the config is JSON.
- Every Herdr call goes over the socket at `HERDR_SOCKET_PATH` (one request per
  connection, plus one long `events.subscribe` connection), like image-viewer. Socket
  replies have the CLI's JSON shape (`result`, or `error {code, message}`). There is no
  socket `pane.run`: a shell command is `pane.send_input {text, keys: ["Enter"]}`
  (verified). `HERDR_SOCKET_PATH` is injected in plugin panes and in every pane shell,
  so the shell subcommands (`park`, `resume`, `compact`) have it too; without it the
  plugin says it is not running inside Herdr.
- No user-specific paths or hostnames. Every default is configurable.
- `platforms = ["linux", "macos"]`, `min_herdr_version = "0.9.1"`. Windows is out
  (`ps` and the named-pipe transport differ).
- Records and logs live in `HERDR_PLUGIN_STATE_DIR` (only when `HERDR_PLUGIN_ID` is this
  plugin; otherwise `${XDG_STATE_HOME:-$HOME/.local/state}/herdr/plugins/<id>`). Never
  inside the plugin root.
- The dashboard redraws the whole screen (a few dozen lines); key input, polling and
  the event stream share one `select` loop.
- Unexpected exceptions are written to `dashboard.log` in the state directory before
  the process exits.
- MIT. `unittest`, `scripts/test.sh`.

## UI and keys

The `[[panes]]` entrypoint defaults to `placement = "overlay"` (full size over the
current pane; closing it restores the previous focus and zoom). The `open-tab` action
uses `plugin pane open --placement tab` for people who keep it open. Popups are not
used: they have no `HERDR_PANE_ID` and block moving to other panes while open.

```
 Agent parking  ·  9 claude  ·  2.1 GB  ·  codex: 5 (not managed)          [?] help
 ──────────────────────────────────────────────────────────────────────────────────
   place            name                     status   idle    ctx           rss   ver
 ▶ w8/t3/p36 web    api gateway refactor     idle     ≥1h12m  37k 18%       205M  2.1.283
   w8/t4/p3A        invoice import fix    done     3h05m   compacted 2h  192M  2.1.281 old
   wD/t5/p20        docs cleanup      working  —       112k          370M  2.1.283
   wJ/t1/pS  infra  release checklist            blocked  12m     54k 27%       169M  2.1.283
   wD/t2/p2T  💤    color pipeline notes      parked   2d      compacted 2d  —     2.1.280
                    ↳ 2026-09-24 21:10  "stopped before pasting the table into the wiki"
   (no pane)  💤    billing rollout check    parked   5d      41k           —     2.1.278
 ──────────────────────────────────────────────────────────────────────────────────
 s park  c compact  C compact+park  r resume  R swap  g go  S idle≥60m  n note  x forget  / filter  q
```

Park confirmation:

```
 park w8/t3/p36  "api gateway refactor"  (idle ≥1h12m, 37k 18%, 205M)
 background Bash/monitor tasks and running subagents are lost by parking
 note (empty for none, Ctrl-D or blank line to finish):
 >
```

Compact confirmation:

```
 compact w8/t3/p36  "api gateway refactor"  (37k 18%)
 preparation report (last reply, first lines):
   Saved the port map to memory; committed 2 files (a1b2c3d) and pushed.
   No temporary files or processes left.
 focus (one line; sent as /compact <focus>, empty sends /compact):
 > keep the port map and the open TODO list
 Enter to compact, e to edit, Esc to cancel
```

Resume confirmation:

```
 resume wD/t2/p2T  "color pipeline notes"  parked 2d ago, compacted 2d
 cwd   /path/to/project
 claude --resume 5e0c...  (flags: --effort medium)
 note:
   stopped before pasting the table into the wiki
 Enter to resume, e to edit note, Esc to cancel
```

Bulk park:

```
 park sessions idle for 60m or more (edit: 60):
   [x] w8/t3/p36  api gateway ...  ≥1h12m
   [x] w8/t4/p3A  invoice import ... 3h05m
   [ ] wJ/t1/pS   release checklist      12m (blocked, skipped)
 note for all (optional):
 Enter to park 2 sessions, Esc to cancel
```

- Keys: two `[[actions]]` (`open`: overlay, `open-tab`: tab), `contexts = ["global"]`.
  Users bind them in `config.toml` with
  `[[keys.command]] type = "plugin_action" command = "haretoke.agent-parking.open"`;
  the README shows an example. A plugin cannot register keys itself (the manifest has
  no keybinding field).

## Data model

State directory:

```
<state>/
  records/<uuid>.json      parked (parking / parked / park_failed / resume_pending / resume_failed)
  records/broken/          unreadable records, set aside
  resumed/<uuid>.json      resumed (history, deleted after 30 days by default)
  observed.json            idle tracking (written by the dashboard)
  context-windows.json     optional: {session_id: context_window_size} written by the user's statusline
  dashboard.log
```

Record (schema_version 1):

```json
{
  "schema_version": 1,
  "session_id": "5e0c4b3e-....",
  "title": "color pipeline notes",
  "cwd": "/path/to/project",
  "argv": ["/home/u/.local/bin/claude", "--effort", "medium"],
  "claude_version": "2.1.280",
  "claude_executable": "/home/u/.local/share/claude/versions/2.1.280",
  "pane_id": "wD:p2T",
  "pane_id_history": [],
  "tab_id": "wD:tY",
  "tab_label": "2",
  "workspace_id": "wD",
  "workspace_label": "project",
  "label_before": null,
  "layout_hint": {"sibling_pane_id": "wD:p2S", "position": "second", "direction": "right", "ratio": 0.5, "path": []},
  "status": "parked",
  "parked_mode": "keep",
  "status_at_park": "idle",
  "idle_seconds_at_park": 4320,
  "idle_lower_bound": true,
  "rss_kb_at_park": 209920,
  "context_at_park": {"tokens": 36890, "percent": 18, "compacted_at": null},
  "parked_at": "2026-09-24T12:10:00Z",
  "note": "stopped before pasting the table into the wiki",
  "resumed_at": null,
  "error": null
}
```

- The key is `session_id`. Pane / tab / workspace IDs are hints; without them the
  session is recreated from cwd and labels.
- An unknown `schema_version` is neither read nor deleted (as in image-viewer).
- Broken JSON is moved to `records/broken/` and listed as "broken record".

Config `HERDR_PLUGIN_CONFIG_DIR/config.json` (every key optional):

| Key | Default | Meaning |
|---|---|---|
| `poll_seconds` | 2 | List refresh interval |
| `exit_timeout_seconds` | 20 | How long to wait for the shell after `/exit` |
| `start_timeout_ms` | 30000 | `--timeout` for `agent start` |
| `on_park` | `"keep"` | What happens to the parked pane: `keep` (empty shell and label) or `close` (close it, recreate on resume) |
| `parked_label_format` | `"💤 {title}"` | Label of a parked pane; `{title}` and `{short_id}` are available; cut at 80 characters |
| `send_note_as_prompt` | false | Send the note as the first prompt after a resume |
| `bulk_idle_minutes` | 60 | Default threshold for `S` |
| `claude_command` | `"claude"` | Fallback executable for the `old` badge when `readlink` of the running process does not apply (resolved on `PATH`) |
| `resumed_keep_days` | 30 | Retention of resumed records |
| `records_dir` | the state directory | Where records live, for containers that want them on a bind mount |
| `claude_config_dir` | `$CLAUDE_CONFIG_DIR` or `~/.claude` | Where `projects/*/<uuid>.jsonl` transcripts are searched |
| `context_window_by_model` | `{}` | Model id prefix → context window in tokens (`{"claude-haiku": 200000}`), used for the ctx percentage |
| `prepare_command` | `"/prepare-compact"` | What `c` / `C` send first |
| `prepare_prompt` | null | When set, this text is sent instead of `prepare_command`, with no fallback. When unset, a missing skill (`Unknown command`) makes the flow send the built-in text instead |
| `prepare_timeout_seconds` | 600 | How long to wait for the preparation to finish |
| `compact_timeout_seconds` | 300 | How long to wait for the new `compact_boundary` line |

## Errors and edge cases

| Situation | Behaviour |
|---|---|
| Park on `working` / `blocked` / `unknown` | Refused. `blocked` says "clear the approval first" |
| A Claude pane without `agent_session` (integration missing or old) | Cannot park. Says "`herdr integration install claude` is required" |
| The shell does not come back after `/exit` (timeout) | `park_failed`. The pane is left alone; the record stays (the UUID is right, so `r` works once a person exits) |
| `/exit` sent while Claude waits in another dialog (for example "Resume from summary") | Same as the timeout. `agent prompt` returns `agent_blocked` for `blocked`, so most cases are refused up front |
| A half-typed line in Claude's input box | Refused (park step 1) so `/exit` is not submitted together with it |
| Background Bash / monitor tasks or running subagents | Lost by parking (Claude's behaviour; a resume does not bring them back). Without hooks v1 cannot detect them, so the park confirmation always carries the warning. Later: the `Stop` hook's `background_tasks` / `session_crons` (keys verified) or the foreground process group |
| The preparation becomes `blocked` | The compact flow stops; the dashboard says to go to the pane. `c` again continues from the focus extraction when a tag exists |
| The preparation reply has no focus tag | The focus is empty in the confirmation and can be typed |
| The new `compact_boundary` line does not appear in time | `compact_failed` is shown; nothing else is changed. `C` does not park |
| Another command is running in the resume pane | Refused. `g` to look |
| `agent start` returns `agent_not_ready` (trust dialog, first time in a folder) | `resume_pending`; answer the dialog, then `r` |
| `agent start` times out | `resume_failed`; the last 10 lines of `pane read` are shown |
| `agent_session` after the resume is a different UUID | Warn; the record is not `resumed` (`resume_failed`, both IDs in `error`) |
| The same UUID resumed in two panes | There is one record, so the second is "already resumed". Right before `r` every Claude pane is matched again; if the UUID runs elsewhere, no second process is started, the record becomes `resumed` and the pane is pointed out |
| The cwd is gone | No recreate; the reason is shown (`claude --resume` itself works from any directory, so the README describes starting it by hand elsewhere) |
| The pane already has a label | Kept in `label_before`, overwritten while parked, restored on resume |
| `on_park = close` and the pane is the last one of its tab | Not closed, treated as `keep` (`parked_mode = "keep"`); the tab is never closed |
| `on_park = close` and something else is in the foreground after the shell is back | Not closed, treated as `keep`, with a reason |
| The record's pane is gone | "(no pane)" → recreate. A server restart alone does not cause this: pane IDs survive it (spike 0-1) |
| Two dashboards (overlay and tab) | `observed.json`: the last writer wins (atomic rename). Records are one file per UUID, so no collision. Parking the same row twice: the second `agent prompt` fails because Claude is gone, and a record in `parking` is never overwritten |
| Control characters or newlines in the note | Stored as is (JSON); the display drops control characters; never put in a label |
| Long values in `argv` such as `--settings '{...}'` | Stored as is (0600); not shown in the list |
| Transcript unreadable, missing or huge | ctx is empty; the tail read has a byte cap and never loads the whole file |
| Codex panes | Not listed; the footer shows "codex: n (not managed)" |
| Claude `--bg` sessions and sessions under `claude agents` | Not in a pane, out of scope |

## Public plugin considerations

- `herdr-plugin.toml`: `id`, `name`, `version`, `min_herdr_version = "0.9.1"`,
  `platforms`,
  `[[panes]] id = "dashboard" placement = "overlay" command = ["python3", "-m", "agent_parking", "dashboard"]`,
  `[[actions]] id = "open"` / `"open-tab"` (`contexts = ["global"]`). No build commands.
- No dependencies (standard library, `ps`, `herdr`). Without `ps`, RSS is empty.
- Rows missing expected keys are shown as "unknown" so a change in Herdr's JSON does
  not crash the dashboard.
- No hard-coded emoji beyond user-configurable strings (the label format).
- Distribution through devcon-herdr's plugin lock
  (`~/.local/state/devcon-herdr/plugins.lock.json`, `devcon-herdr plugins update` →
  `herdr plugin install owner/repo --ref <commit> --yes`). During development the Mac
  uses `herdr plugin link`.
- The `prepare-compact` skill ships in `skills/prepare-compact/SKILL.md`. devcon-herdr
  distributes it through its skill mirror (the same path as the herdr-pane-viewer
  skill); public users follow the README to copy it into their Claude skills
  directory. The README also recommends a `Compact Instructions` section in
  `CLAUDE.md` for manual `/compact` (documented by Claude Code; in spike 0-20 it
  reached a manual summary but not an automatic one, so the README promises it only
  for manual compaction, which is what the dashboard sends).
- The README states that the Claude integration (`herdr integration status` shows
  `claude: current`) is required, how this relates to `session.resume_agents_on_restore`,
  and that Codex is not supported.
- The GitHub topic `herdr-plugin` lists the repository in the marketplace.

## Security and privacy

- Records hold the session name, cwd, launch argv, context numbers and the note.
  Directories 0700, files 0600. No transcript text is stored; the transcript is only
  read (tail) for the ctx column and the focus tag.
- `argv` may contain secrets or prompt fragments (`--append-system-prompt`, ...). It is
  never shown in the list and `x` deletes the record. The README says so.
- Notes are plain text; the README says not to put secrets in them.
- Text sent into panes: `agent prompt "/exit"`, `agent prompt <prepare_command|prepare_prompt>`,
  `agent prompt "/compact <focus>"`, `pane.send_input` of `printf ...` and of `cd ...` and,
  when enabled, `agent prompt <note>`. Every argument goes through `shlex.quote`; the
  focus is reduced to one line.
- `pane read` is used only to diagnose a failure (last lines) and to check the input
  box; nothing read is stored.
- The plugin runs as the user and can call every `herdr` command. It closes or deletes
  only what it made (labels, recreated panes) and, with `on_park = close`, the pane it
  parked (shell-only foreground, not the last pane of a tab). Other panes and tabs are
  never closed.

## Herdr server restarts

- Herdr restores only panes that have an `agent_session` with `claude --resume <id>`,
  and without the original launch flags (spike 0-2). A parked pane has none, so after
  a restart it is an empty shell with its label and cwd; its scrollback, including
  Claude's `Resume this session with` line, is gone, so the record is the only trace.
- Pane IDs, tab IDs, labels and cwd survive a server restart and closed IDs are not
  reused (spike 0-1), so a record's `pane_id` stays valid across restarts.
- No automatic resume (eating the memory again right after a restart defeats the
  purpose). `resume_on_startup` from `[[startup]]` is a future extension; in v1 a
  person presses `r`.

## Containers (devcon-herdr)

- devcon-herdr does not share `~/.claude` between the Mac and the WSL2 host; it bind
  mounts the WSL2 `~/.claude` into each container. The plugin state directory
  `~/.local/state/herdr/plugins/<id>` is under the container's home and is not a bind
  mount (verified 2026-09-27 in `/proc/self/mountinfo` of the Herdr devcontainer: the
  mounts under the home are `~/.claude`, `~/.codex`, `~/.codex-devcontainer`, a few
  `~/.config/*` and `~/.local/share/agent-skills`) → **records are lost on a container
  rebuild**. Transcripts stay in `~/.claude`, so the `claude --resume` picker still
  finds the sessions.
- A rebuild also removes the Herdr server and its panes, so the records would only
  serve recreate. When wanted, `records_dir` can point at a mounted place (for example
  under `~/.claude`); it is not the default because `~/.claude` belongs to Claude.

## Future extensions

- Codex: the same flow with `codex resume <UUID>` once the daemon behaviour settles
  (what replaces `/exit` is open).
- Cross-server list through `--machine` (asking each server's plugin).
- Records for sessions exited by hand (above).
- Automatic resume from `[[startup]]` (`resume_on_startup`).
- A light resident pane (hidden tab) that only tracks idle time.
- Compacting a parked session without starting its UI:
  `claude -p --resume <uuid> "/compact <focus>" < /dev/null` works (spike 0-17: same
  session, new boundary, focus honoured). It must run with `CLAUDE*` variables unset.
- Bulk park by an RSS threshold.

## Open items

Still unverified:

- `old` detection for npm global and Homebrew installs (not available to test).
- Whether `Compact Instructions` never reaches an automatic summary (one sample).
- `g` with a TUI client attached (spike 0-4 ran without one; the real-device checks
  cover it).

Everything else was settled by the spikes in `plan.md` (0-1 to 0-22).
