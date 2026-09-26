# herdr-agent-parking plan

Herdr plugin that lists the Claude Code panes on this server, stops waiting sessions
with `/exit` (park) and starts them again in the same pane with `claude --resume <UUID>`
(resume), with an optional prepared `/compact` before parking. Records are keyed by
the session UUID; pane / tab / cwd are hints. The design is in `DESIGN.md`.

Same shape as herdr-image-viewer: `herdr-plugin.toml`, a Python package, `tests/`,
`scripts/test.sh` (`/usr/bin/python3` 3.9 and `python3`), MIT, distributed through
devcon-herdr's plugin lock.

## Decisions

- Plugin id `haretoke.agent-parking`, public GitHub repository
  `haretoke/herdr-agent-parking`, package `agent_parking`, MIT. Code, tests and history
  contain no personal paths, hostnames or secrets. The name is agent-neutral; v1
  manages Claude Code only.
- The dashboard's default placement is `overlay`; the `open-tab` action opens it as a
  tab for people who keep it open.
- Documents are in English, like herdr-image-viewer.
- Codex is out of scope (shared daemon; `/exit` only disconnects).
- The resume key is the UUID. Names are never used (`/clear` carries the name over and
  makes duplicates).
- Only `idle` or `done` panes with an empty input box can be parked or compacted.
- The record is written before `/exit` is sent (Herdr's `agent_session` becomes None
  when Claude exits).
- Parked panes are kept by default (`on_park = "keep"`): the empty shell gets the label
  `💤 {title}` with `pane rename` (labels survive the exit) and the label is restored
  on resume. `on_park = "close"` closes the pane and resumes through recreate; the last
  pane of a tab is never closed.
- Resume is `herdr agent start <name> --kind claude --pane <P> -- --resume <UUID> <flags>`,
  `<flags>` being the park-time argv minus resume and naming flags.
- Without the pane, recreate from the record's `layout_hint` / tab / workspace / cwd.
- The note is optional, stored in the record, shown in the list and in the resume
  confirmation, echoed into the pane's scrollback before the resume, and not sent as a
  prompt by default (`send_note_as_prompt = false`).
- Idle time is tracked by the dashboard from `state_change_seq` (Herdr has no time);
  time before tracking began is a lower bound shown with `≥`.
- The ctx column comes from the transcript: tokens always, a percentage when the
  window size is known (`context_window_by_model` or the optional statusline file),
  `compacted <age>` when the last `compact_boundary` has no assistant usage after it.
- `c` compacts (prepare → wait → focus tag → confirm → `/compact <focus>` → boundary),
  `C` compacts then parks, `s` only parks. `S` uses the idle threshold only and includes
  `≥` rows.
- `R` (swap) asks for confirmation when the running version equals the current one.
- RSS is the sum of the foreground process group; the Claude-only value is kept in JSON.
- Codex panes are counted in the footer, not listed.
- Shell-only foreground is `pid == shell_pid`, never the process name (both `-zsh` and
  `zsh` were observed).
- No new Claude hook in the main flow; sessions exited by hand are an optional extension.
- Standard library only; config is JSON (`HERDR_PLUGIN_CONFIG_DIR/config.json`).
- State lives in `HERDR_PLUGIN_STATE_DIR` (only when `HERDR_PLUGIN_ID` is this plugin,
  otherwise `${XDG_STATE_HOME:-$HOME/.local/state}/herdr/plugins/<id>`); never in the
  plugin root. `records_dir` may move the records (default: the state directory; lost
  on a container rebuild).
- The `prepare-compact` skill ships in `skills/prepare-compact/SKILL.md` and is
  distributed by devcon-herdr's skill mirror; public users copy it by hand (README).

## Limits (initial values, tuned after the real-device checks)

| Name | Value |
|---|---|
| list refresh | 2 s |
| wait for the shell after `/exit` | 20 s (measured about 4 s) |
| `agent start` timeout | 30000 ms (Herdr's default) |
| parked pane treatment | `keep` (option `close`) |
| label format | `💤 {title}`, 80 characters (Herdr's cap) |
| bulk park threshold | 60 min |
| resumed records kept | 30 days |
| record schema_version | 1 |
| `pane read` tail for diagnostics | 10 lines |
| preparation wait | 600 s |
| wait for the new `compact_boundary` | 300 s |
| transcript tail read | 1 MiB per read, cached by mtime and size |

## Herdr and Claude facts this design relies on (Herdr 0.9.1, Claude Code 2.1.283)

Verified on a real device (Mac local, 2026-09-26/27) and in the v0.9.1 documentation.

- `pane list` / `pane get` / `agent get` return `agent`, `agent_status`,
  `agent_session {kind:"id", value}`, `cwd`, `workspace_id`, `tab_id`,
  `terminal_title_stripped`. `agent get` and `agent list` carry `state_change_seq`
  (a counter). **No time.** The `pane.agent_status_changed` event has none either
  (`pane_id`, `workspace_id`, `agent_status`, `title`, `state_labels`).
- `agent list` prints JSON as is (`--json` is a usage error).
- `agent_session` becomes None when Claude exits (device). A `pane rename` label stays
  (device).
- `pane process-info --pane <P>` returns
  `foreground_processes[] {pid, argv, argv0, cmdline, cwd, name}` and `shell_pid`. At a
  shell prompt the list holds the shell itself (`-zsh` on one device, `zsh` on
  another), so "shell only" is `pid == shell_pid`. On macOS Claude's `name` is the
  executable's basename, measured `"2.1.283"` (`~/.local/bin/claude` →
  `~/.local/share/claude/versions/2.1.283`). On Linux the Claude entry has no `argv` /
  `argv0` / `cmdline` and `name` is `"claude"`; `/proc/<pid>/cmdline` and
  `/proc/<pid>/exe` have what is missing (spike 0-10). Claude is the foreground group
  leader. No RSS → `/proc/<pid>/status` or `ps -o rss= -p` (KiB, spike 0-9). MCP
  servers and `caffeinate` share the foreground group.
- `agent prompt <P> "/exit"` ends Claude; the shell is back in about 4 s (device).
  `blocked` returns `agent_blocked` without sending (docs).
- `agent start <name> --kind claude --pane <P> [--timeout MS] -- <args>` starts in a pane
  whose shell owns the foreground and waits until ready; a trust dialog gives
  `agent_not_ready` (device). Names match `[a-z][a-z0-9_-]{0,31}` and are unique among
  live agents (docs). Resuming this way fires `SessionStart source=resume` with the
  same UUID and re-registers `agent_session` (device).
- `claude --session-id <existing UUID>` exits with "Session ID ... is already in use"
  (device). `/compact` keeps the UUID; `/clear` mints a new one and carries the
  `session_title` over (device).
- `pane split <P> --direction right|down [--ratio FLOAT] [--cwd PATH] [--no-focus]`,
  `tab create [--workspace W] [--cwd PATH] [--label TEXT] [--no-focus]` (result has
  `root_pane.pane_id`), `workspace create [--cwd PATH] [--label TEXT] [--no-focus]`
  (docs; `tab create` on a device).
- The `pane focus` CLI only takes `--direction`. Focusing a given pane is the socket
  method `pane.focus` with `{pane_id}` (API schema). Whether focus survives closing an
  overlay is a spike.
- `pane.exited` appears to mean the pane's root process (the shell) exited, not the
  foreground child; Claude's exit shows as `pane.agent_status_changed` or as `agent`
  disappearing from `pane get`.
- Plugin panes: `placement` is `overlay` (default) / `popup` / `split` / `tab` / `zoomed`
  (docs). A popup has no `HERDR_PANE_ID` and is session-modal. A pane process gets
  `HERDR_SOCKET_PATH`, `HERDR_BIN_PATH`, `HERDR_PLUGIN_ID`, `HERDR_PLUGIN_ROOT`,
  `HERDR_PLUGIN_CONFIG_DIR`, `HERDR_PLUGIN_STATE_DIR`, `HERDR_PLUGIN_CONTEXT_JSON` and
  its own `HERDR_PANE_ID`, and starts in the plugin root (docs; image-viewer spike).
  Every `herdr` command is available to a plugin (docs).
- `[[actions]]` `contexts` are `global` / `workspace` / `tab` / `pane` / `selection`
  (API schema). Keys are bound by the user with `[[keys.command]] type = "plugin_action"`;
  the manifest has no key field.
- `[[startup]]` runs once after the API is ready and exits; `[[events]]` starts a
  command per event; there is no scheduler (docs).
- `events.subscribe` keeps the socket open and streams `pane.agent_status_changed`,
  `pane.closed`, `pane.exited` and others (docs; API schema EventKind).
  `pane.agent_status_changed` needs a `pane_id` per subscription; `pane.agent_detected`
  works without one and reports both arrival and release (`released: true`) (spike 0-6).
- `herdr plugin config-dir <id>` is `~/.config/herdr/plugins/config/<id>` (device);
  state is `~/.local/state/herdr/plugins/<id>` (image-viewer spike). In containers
  neither is believed to be a bind mount: devcon-herdr's comments say only `~/.claude`
  is mounted; devcontainer.json was not read.
- `session.resume_agents_on_restore` (default true) restores only panes with an
  `agent_session` (docs). Parked panes are not among them.
- Claude's statusline `used_percentage` is
  `(input_tokens + cache_creation_input_tokens + cache_read_input_tokens) / context_window_size`,
  truncated (36,890 / 200,000 → 18); output tokens are not counted (device, docs).
  The statusline stdin JSON carries `session_id` and
  `context_window.context_window_size`; right after a compaction `current_usage` and
  `used_percentage` are null until the next API call (device, docs).
- Transcripts are `<claude_config_dir>/projects/<slug>/<uuid>.jsonl`. `assistant`
  lines carry `message.model` and `message.usage` with the three input fields (device).
  A compaction writes a `type: "system"`, `subtype: "compact_boundary"` line with
  `timestamp` and `compactMetadata {trigger, preTokens, postTokens}`, followed by the
  summary as a `type: "user"` line with `isCompactSummary: true` (device). The window
  size is not in the transcript; the docs say 200000 by default and 1000000 for
  extended-context models (haiku 200k; an Opus 5.5 session used 279k).
- Claude's `Stop` hook stdin carries `background_tasks`, `session_crons` and
  `permission_mode`; `SessionStart` carries `session_title`; hooks see `HERDR_PANE_ID`
  and `CLAUDE_CODE_SESSION_ID` (device). Not used by v1, noted for the extension.

## Structure

- `records`: reading and writing records (UUID validation, schema_version, atomic
  rename, 0600, setting broken JSON aside, moving to `resumed/`, expiry).
- `config`: `config.json` with defaults; invalid values fall back to the default and
  are logged.
- `state`: the state and config directories (the same rule as image-viewer's `state`).
- `herdr_api`: one-shot commands through `HERDR_BIN_PATH` (`pane list/get/process-info/
  layout/rename/run/read/split/close`, `agent list/get/read/prompt/start/wait`,
  `tab list/create/focus`, `workspace list/create`), the socket `pane.focus`, and the
  socket `events.subscribe`. Missing keys are handled here.
- `transcript`: locating a session's transcript by glob, tail reading with a cache,
  the context numbers, the compacted state and its age, the window size resolution,
  and the focus tag after a given prompt.
- `inventory`: rows from `pane list` + `agent list` + `process-info` + `ps` +
  `transcript`; excludes non-Claude panes and the dashboard; the `old` badge
  (`readlink` of the running `argv[0]`, fallback `claude_command`); reconciliation of
  records against every Claude pane.
- `idle`: idle tracking (`observed.json`, `state_change_seq`, lower-bound flag,
  injectable clock).
- `park`: the park procedure (checks → `layout_hint` → record → `/exit` → wait for the
  shell → label or close).
- `compact`: the compact flow (prepare → wait → focus tag → confirmation → `/compact` →
  boundary), retry, `blocked`.
- `resume`: the resume procedure (pane check → note → `cd` → `agent start` → UUID check
  → label → record move), recreate, `agent_not_ready`.
- `argv`: pure function removing resume and naming flags from a launch argv.
- `dashboard`: the pane process; drawing, keys, confirmations, note input, polling and
  the event stream in one `select` loop.
- `cli`: `dashboard`, `open` (action: overlay), `open-tab` (action: tab), `list`
  (rows as JSON for scripts), `park <pane>`, `compact <pane>`, `resume <uuid>`
  (usable without the dashboard).
- `skills/prepare-compact/SKILL.md`: the preparation skill (English).
- `herdr-plugin.toml`: the `dashboard` pane (overlay), the `open` / `open-tab` actions,
  `min_herdr_version = "0.9.1"`, platforms linux and macos.

## Tests

Mark a test `[x]` when it passes. Structural and behavioral changes are committed
separately. Mocked Herdr behavior never replaces the real-device checks at the end.

### 0. spike (manual, record the findings here before the TDD steps)

Use a throwaway session: start `herdr --session parking-spike server`, run every
command with `--session parking-spike`, and finish with
`herdr session stop parking-spike` and `herdr session delete parking-spike`. The main
server is never restarted.

- [x] in the throwaway session, `pane split` / `tab create --cwd` / `workspace create --cwd`,
      then `herdr --session parking-spike server stop` and a restart: record how pane IDs,
      tab IDs, `pane rename` labels and cwd come back (if IDs change, matching relies on
      cwd + label)
      (2026-09-27, Mac local, Herdr 0.9.1): workspace `w1` with a split (`w1:p1`,
      `w1:p2`) and a second tab; in that tab `w1:p4` was split off and `w1:p3` closed to
      leave a gap; `w1:p2` did `cd` to another directory. After `server stop` and a
      restart, `workspace list` / `tab list` / `pane list` were identical: pane IDs
      (gap included), tab IDs and labels, workspace label, pane labels (the `💤` one
      included) and the cwd after the `cd`. The next split after the restart became
      `w1:p5`, so closed IDs are not reused across a restart either. Records can
      trust `pane_id` after a server restart; cwd + label matching stays a fallback for
      closed panes only
- [x] start `claude` in a throwaway pane and `/exit`; after a restart, what the parked
      pane is (empty shell, label, `agent_session`)
      (2026-09-27, Mac local, Herdr 0.9.1, Claude Code 2.1.283): two panes in one tab,
      `w1:p1` with a running Claude (`claude --model haiku`, one prompt answered) and
      `w1:p2` labelled `💤 parked-label` whose Claude answered one prompt and then got
      `/exit`. Before the restart `session.json` held `agent_session` only for `w1:p1`;
      `w1:p2` kept its label and nothing else. After `server stop` and a restart:
      - `w1:p2` came back as an empty shell (one foreground process, `pid == shell_pid`),
        label and cwd intact, `agent_session` None, and its screen held only a fresh
        prompt. The `Resume this session with: claude --resume <uuid>` line Claude
        printed on `/exit` was gone: the scrollback does not survive a restart, so the
        plugin's record is the only trace of a parked session after one.
      - `w1:p1` was resumed by Herdr on its own as `claude --resume <uuid>` (same UUID,
        `agent_session` reported again, status idle). The launch flags were dropped
        (`--model haiku` was not in the new argv); the model stayed Haiku because the
        session remembers it, but other flags (`--settings`, `--add-dir`,
        `--mcp-config`, ...) would be lost. So a session parked after a Herdr restore
        has an argv without its original flags, and the record cannot restore them.
      - Environment caveat for later spikes: a server started from inside a Claude
        session hands `CLAUDE_CODE_*` to its pane shells, and a Claude started there
        shows "Transcript saving is off" and cannot be resumed. The throwaway server
        has to start with every `CLAUDE*` and `HERDR_*` variable unset
      - Isolation caveat: `herdr plugin link` writes to the plugin registry under
        `~/.config/herdr`, which every session shares (`herdr --session <s> plugin list`
        showed the user's plugins). From spike 0-3 on, the throwaway server runs with
        its own `XDG_CONFIG_HOME` (a short path such as `~/.cache/hps`, because the
        socket path has to fit `sun_path`; a scratch path under `/private/tmp/...` was
        too long), so probe plugins never enter the user's registry
- [x] from an overlay plugin pane, `agent prompt` / `agent start` / `pane rename` /
      `pane run` work against another pane
      (2026-09-27, Mac local, isolated throwaway session): a probe plugin
      (`placement = "overlay"`, `python3 probe.py`, targets passed with
      `plugin pane open --env`) drove three panes of the same tab and logged each call.
      All returned rc 0 and took effect: `pane rename` set the label, `pane run` ran
      `echo` in the shell pane, `agent prompt ... --wait` got Claude to answer (4.6 s),
      and `agent start probe-start --kind claude -- --model haiku` started Claude in an
      empty pane (3.9 s, idle, `agent_session` reported). The overlay pane got its own
      `HERDR_PANE_ID` (`w1:p4`), cwd = plugin root, `HERDR_BIN_PATH`,
      `HERDR_SOCKET_PATH`, `HERDR_SESSION`, the `HERDR_PLUGIN_*` set and
      `HERDR_PLUGIN_CONTEXT_JSON` whose `focused_pane_id` was the pane under the overlay
      (`w1:p1`). When `probe.py` exited the overlay closed and focus went back to
      `w1:p1`
- [x] from inside the overlay, socket `pane.focus {pane_id}` onto pane X in another tab,
      then exit the dashboard: does focus stay on X or does the overlay's "restore the
      previous focus" take it back? If it does, `g` is limited to tab / zoomed placements
      or sends `pane.focus` from a detached process after exit
      (2026-09-27, Mac local, isolated throwaway session without a TUI client): the
      overlay (`w1:p6`, over `w1:p1` in tab `w1:t1`) sent
      `{"method":"pane.focus","params":{"pane_id":"w1:p5"}}` on the raw socket for a pane
      in tab `w1:t2`. The reply was `pane_info` with `focused: true`, `pane list` showed
      only `w1:p5` focused, and after the overlay exited focus stayed on `w1:p5` with
      `w1:t2` the focused tab. Tab `w1:t1` was left unzoomed with its own focused pane
      back on `w1:p1`. So the overlay's restore does not undo an explicit focus: `g` can
      send `pane.focus` and exit, in the overlay too, without a detached process.
      `pane.focus` is in the API schema (`herdr api schema --json`) although the socket
      doc's method table lists only `pane.focus_direction`; the CLI has no pane-id focus.
      Not checked with a TUI client attached; the real-device `g` check covers that
- [x] what `[[events]]` `pane.exited` reports (root shell or foreground child)
      (2026-09-27, Mac local, isolated throwaway session): the probe plugin hooked
      `pane.exited`, `pane.closed` and `pane.agent_status_changed` and ran
      `pane get` inside each hook. A foreground child exiting (`sleep 1`) fired
      nothing. Claude's `/exit` fired no `pane.exited`, only
      `pane.agent_status_changed` with `agent_status: "unknown"` and no `agent` key.
      `exit` in the root shell fired `pane.exited`
      (`{"event":"pane_exited","data":{"pane_id":..,"workspace_id":..}}`) and the pane
      was already gone in the hook (`pane_not_found`); no `pane.closed` was logged for
      it. So `pane.exited` means the pane's root process ended and the pane closed;
      the end of Claude is `agent_status_changed` to `unknown` without an `agent`
- [x] with the dashboard open as a tab, a status change of a Claude in another tab is
      seen both through `events.subscribe` (`pane.agent_status_changed`) and through
      `state_change_seq` in `agent list`
      (2026-09-27, Mac local, isolated throwaway session): a probe opened with
      `--placement tab` subscribed on the raw socket and polled `agent list` every
      second while Claude in another tab started, answered once and got `/exit`.
      - `pane.agent_status_changed` cannot be subscribed for all panes: without
        `pane_id` the request fails (`invalid request: missing field pane_id`). Every
        other type tried (`pane.agent_detected`, `pane.created`, `pane.updated`,
        `pane.closed`, `pane.exited`, `layout.updated`, `tab.created`) accepts no
        `pane_id`. Several subscriptions share one request (`subscriptions` list).
      - With `[{agent_status_changed, pane_id}, {agent_detected}]` the stream showed
        `pane_agent_detected` (`agent: "claude"`) on start, then `idle`, `working`,
        `idle`, and on `/exit` a second `pane_agent_detected` with
        `released: true, final_status: "idle"` followed by `unknown`. So the global
        `pane.agent_detected` reports every Claude arriving and leaving.
      - Polling saw `state_change_seq` 18 → 20 → 21 with the statuses; a 1 s poll
        skipped seq 19 (a short `idle`), and after `/exit` the row simply left
        `agent list`. Polling is enough for idle time (seconds); the stream adds the
        exact moments.
      - The dashboard therefore subscribes to `pane.agent_detected` globally plus one
        `pane.agent_status_changed` per Claude pane, and reopens the subscription when
        the set of Claude panes changes; polling `agent list` stays the base
- [x] `agent start ... -- --resume <UUID> --effort medium` shows the extra flags as is in
      `process-info` (a swap round trip neither adds nor drops argv)
      (2026-09-27, Mac local, isolated throwaway session): `agent start ev7 --kind claude
      -- --model haiku --effort low` gave argv
      `[<abs path>/claude, --model, haiku, --effort, low]`; after one prompt and `/exit`,
      `agent start ev7 --kind claude -- --resume <uuid> --model haiku --effort low` gave
      `[<abs path>/claude, --resume, <uuid>, --model, haiku, --effort, low]` with the same
      UUID in `agent_session`. The args pass through verbatim and in order, `argv[0]` is
      the absolute path of `claude` (not the bare name typed), and removing the
      executable and `--resume <uuid>` gives back the original flags, so a swap round
      trip is stable
- [x] right after Claude exits, whether `HERDR_PLUGIN_EVENT_JSON` of an
      `[[events]] on = "pane.agent_status_changed"` / `"pane.exited"` hook still holds
      `agent_session` (if so, the "exited by hand" extension is possible; optional)
      (2026-09-27, same run as the `pane.exited` spike): no. The event on `/exit` was
      `{"type":"pane_agent_status_changed","pane_id":..,"workspace_id":..,"agent_status":"unknown"}`
      with no session, and `pane get` inside the hook already returned `agent: null`,
      `agent_session: null`. While Claude ran, every status event's `pane get` did carry
      `agent_session`, so an event hook that remembers the last UUID per pane on each
      `idle` / `done` / `working` event could still record a hand-made `/exit`; the
      hook alone at exit time cannot. The optional extension, if built, keeps that
      last-seen map
- [x] `ps -o rss= -p <pid>` units on macOS (KB) and in a Linux container (KB)
      (2026-09-27): the macOS `ps(1)` page gives `rss` "in 1024 byte units". In the
      Herdr devcontainer (Debian 13, procps `/usr/bin/ps`) `ps -o rss= -p 1` printed 48
      and `/proc/1/status` said `VmRSS: 48 kB`, so both are KiB. Slim Linux images can
      lack procps, so on Linux the plugin reads `VmRSS` from `/proc/<pid>/status`
      (no dependency) and uses `ps` only where `/proc` is missing (macOS)
- [x] `old` detection: `os.readlink` of the running process's `argv[0]`
      (`~/.local/bin/claude`) gives the current `versions/<v>`, compared with
      `process-info`'s `name` (the version at launch). What happens with npm global or
      Homebrew installs; otherwise resolve `claude_command` on `PATH`, and without that
      no badge (the plugin runs in the Herdr server's environment, so a container's
      `PATH` may not hold the user's `claude`)
      (2026-09-27, native installer on the Mac and in the Herdr devcontainer; read-only
      on both live servers):
      - macOS: for all 9 Claude panes `process-info` gave `argv` and `name` = the
        running executable's version, matching `lsof` txt
        (`~/.local/share/claude/versions/<v>`): 3 on 2.1.283, 4 on 2.1.282, 2 on 2.1.281
        and 2.1.280. `readlink ~/.local/bin/claude` gave the current 2.1.283, so 6 of 9
        would show `old`. `ps -o comm=` only shows the symlink path, not the version.
      - Linux (Debian 13 container, Herdr 0.9.1): `process-info` gave the Claude
        process **without `argv`, `argv0` or `cmdline`**, with `name: "claude"`, and
        with `pid == foreground_process_group_id`. `/proc/<pid>/cmdline` was readable
        and held the args (`claude --resume <name>`, `claude --worktree <w> --resume
        <uuid>`), `/proc/<pid>/comm` was `claude`, and `readlink /proc/<pid>/exe` gave
        `~/.local/share/claude/versions/<v>` (2.1.280, 2.1.281 while the current link
        pointed at 2.1.282).
      - So: find the Claude process as the foreground group leader
        (`pid == foreground_process_group_id`), take its argv from `process-info` or
        else `/proc/<pid>/cmdline`, and its running version from `/proc/<pid>/exe` on
        Linux or `name` on macOS when it looks like a version. The current version is
        the `realpath` of `argv[0]` when that is a path, else of `claude_command` on
        `PATH`, else of `~/.local/bin/claude`; no badge when either side is unknown.
        npm global and Homebrew installs were not available to test; they fall to "no
        badge" unless a version appears in the executable path
- [x] `ps -o rss=` for the Claude pid alone versus the sum over `foreground_processes`
      (MCP servers, `caffeinate`; 4 processes measured in one group)
      (2026-09-27, the 9 Claude panes of the Mac's live server, read-only): Claude alone
      118–357 MB, the whole foreground group 131–374 MB, i.e. 13–24 MB more from 2–4
      extra processes (the stdio MCP servers' `node`, and `caffeinate`). Parking frees
      the group, so the column shows the sum; the Claude-only value is a JSON field
- [x] after `pane run <P> "printf ..."` shows the note, `agent start` does not return
      `agent_not_ready` (the shell stays in the foreground)
      (2026-09-27, isolated throwaway session): after `pane run <P> "printf '%s\n'
      '💤 note: ...'"` the pane's only foreground process was the shell
      (`pid == shell_pid`), and `agent start -- --resume <uuid> --model haiku` returned
      idle with the same UUID. Claude's full-screen UI then covered the note (it was no
      longer in `pane read --source recent`), so the dashboard's confirmation box stays
      the main place for the note, as designed
- [x] `agent prompt <P> "/exit"` with a half-typed line in Claude's input box (is
      `/exit` appended and submitted with it?), and how `agent read` tells an empty input
      box (the shape of the prompt line). As the alternative, exiting by keys
      (`agent send-keys <P> C-c C-c`; the first Ctrl+C clears the input box): its
      reliability and the SessionEnd `reason` (other than `prompt_input_exit`?)
      (2026-09-27, Claude Code 2.1.283, isolated throwaway session):
      - Yes, it is appended and submitted: with `half typed line` in the box,
        `agent prompt <P> "/exit"` sent `half typed line/exit` as a prompt, Claude
        answered it and kept running (status `done`). Parking must never send `/exit`
        over a draft.
      - The input box is the last line starting with `❯` between two `─` rules. Empty
        is `❯` alone, but a fresh session shows a placeholder (`❯ Try "..."`) that
        plain text cannot tell from typed text. `agent read --format ansi` can: the
        placeholder is wrapped in `ESC[2m` (dim), typed text is not. So "empty" =
        nothing after `❯ ` except dim-styled text.
      - Keys: one `C-c` cleared the draft; a second `C-c` a second later did not exit;
        two `C-c` 0.3 s apart on an empty box exited, with SessionEnd reason
        `prompt_input_exit` (same as `/exit`). The double press depends on a short
        window, so parking keeps `/exit` on an empty box and refuses a draft (the person
        can clear it with `g` and Ctrl+C); keys are not the default path
- [x] `claude --resume <UUID>` while the same UUID runs in another pane (an error like
      `--session-id`, a second process, or a fork?)
      (2026-09-27, Claude Code 2.1.283): a second process. With the session running in
      `w1:p1`, `agent start -- --resume <same uuid>` in `w1:p3` returned idle, both
      panes reported the same `agent_session`, and a prompt answered in `w1:p3` was
      appended to the same transcript file (no fork, no error). Two live processes then
      write one transcript while each keeps its own context. The dashboard must check
      every Claude pane for the UUID right before `r` and never start a second one
      (already in the reconcile design)
- [x] for `on_park = close`: whether `pane layout` yields the neighbour and the split
      direction and ratio; whether `pane split` has left / up; whether `--ratio` restores
      the size; how close a recreate gets in nested splits (3 or more panes)
      (2026-09-27, isolated throwaway session, 120x40 tab):
      - `pane layout` gives pane rects and a flat `splits` list (`direction`, `ratio`);
        `layout.export` gives the BSP tree (`split` nodes with `direction`, `ratio`,
        `first`, `second`; `pane` nodes with `pane_id`, `cwd`), which is what
        `layout_hint` needs: the sibling, first/second, direction, ratio.
      - `pane split` has only `right` / `down` (no left / up). `layout.set_split_ratio`
        takes `path` as booleans (`[true]` = the second child), not strings.
      - Sibling is a single pane, parked pane second (`A | (B / C)`, park C): split B
        `down --ratio 0.7` gave rects identical to the original.
      - Sibling is a single pane, parked pane first (`A | B` at 0.3, park A): split B
        `right`, `pane.swap {source_pane_id: new, target_pane_id: B}`, then
        `set_split_ratio path [] 0.3` gave identical rects. (`pane.swap` needs
        `source_pane_id`; `pane_id` alone is rejected.)
      - Sibling is a subtree (`A | (B / C)` park A, or `(A / B) | C` park C): closing
        collapses the split and a right/down split of one pane cannot recreate a
        position beside the whole subtree; the best available result has a different
        structure. So recreate is exact only when the sibling is a single pane.
      - `layout.apply` rebuilds a whole tab and drops live PTYs, so it cannot be used
- [x] whether `pane close` on the last pane of a tab closes the tab (the reason to keep
      that pane even with `on_park = close`)
      (2026-09-27): yes. Closing the only pane of a new tab removed the tab from
      `tab list`. `on_park = close` keeps such a pane, as designed
- [x] whether a parked session can be compacted headless
      (`claude -p --resume <uuid> "/compact"`; `/compact` is not in the documented list of
      slash commands available with `-p`). If it works, parked sessions can be compacted
      later (future extension)
      (2026-09-27, Claude Code 2.1.283, haiku, no Claude running on that session): yes.
      `claude -p --resume <uuid> --model haiku "/compact keep only the word HEADLESS"
      < /dev/null` exited 0 and appended a second `compact_boundary` (`trigger: manual`,
      same `sessionId`, rows marked `entrypoint: sdk-cli`) to the same transcript; the
      summary honoured the focus and no assistant line followed, so the session reads as
      compacted. Without `< /dev/null` it waits 3 s for stdin and warns. Must be run with
      `CLAUDE*` variables unset (see spike 0-2). So a parked session can be compacted
      later without starting its UI (future extension: `c` on a parked row)
- [x] what happens when `/prepare-compact` is sent where the skill is not installed
      (how an unknown slash command is handled)
      (2026-09-27, tested with `/no-such-skill-xyz`): Claude shows `Unknown command:
      /no-such-skill-xyz` locally, nothing goes to the model, a `system` /
      `informational` line is added to the transcript, and `agent prompt --wait` returns
      `agent_prompt_stalled` (no working state within 5 s). The compact flow treats
      `agent_prompt_stalled` + `Unknown command: <prepare_command>` on screen as "skill
      missing", sends `prepare_prompt` instead, and says so in the confirmation box
- [x] whether a resume or hook activity alone, without any user action, appends lines to
      the transcript (if not, the time of the last conversation line can feed idle time;
      if so, which line types are usable)
      (2026-09-27): a resume followed by 10 s idle added no line (65 → 65, the Herdr
      integration's SessionStart hook included). `/exit` added three lines without a
      timestamp (`file-history-snapshot`, `cost-state` ×2). A `/compact` adds bookkeeping
      lines (`last-prompt`, `ai-title`, `mode`, `permission-mode`, `atis-latch`,
      `attachment`) around the boundary. So the last conversation time is the
      `timestamp` of the last `user` / `assistant` line that is not `isMeta`; it can feed
      idle time for panes the dashboard has not watched, instead of the `≥` lower bound
- [x] whether `Compact Instructions` in `CLAUDE.md` also applies to automatic compaction
      (2026-09-27, haiku, one run each, a `## Compact Instructions` section asking for the
      codeword `PINEAPPLE-42` in every summary): manual `/compact` (headless) put the
      codeword in the summary. Automatic compaction did not: in `-p` mode it never fired
      (154k context with `--autocompact 100k`, two turns, no boundary); interactively
      (`--autocompact 100k`, the same session) it fired (`trigger: auto`, 155139 →
      4716 tokens) and its summary lacked the codeword. One sample, but the README should
      only promise the section for manual `/compact`
- [x] how to tell that `agent prompt "/compact <focus>"` finished: the `working → idle`
      transition or the new boundary line
      (2026-09-27): `agent prompt <P> "/compact keep the LAG words" --wait` returned
      `done` after 16.3 s, and the new `compact_boundary` was already in the transcript
      at that moment. The flow waits with `--wait` and then confirms that the boundary
      count grew; the boundary is the proof, the wait is the trigger to look
- [x] the lag between `Stop` and the transcript when the preparation reply is read (is
      the assistant text already written?)
      (2026-09-27, 3 tries): each time `agent prompt ... --wait` returned, the assistant's
      reply text was already in the transcript. The flow reads right after the wait and
      retries once after 0.5 s only if the reply is missing

### state / config
- [ ] the state directory is `HERDR_PLUGIN_STATE_DIR` only when `HERDR_PLUGIN_ID` is this
      plugin, otherwise `${XDG_STATE_HOME:-$HOME/.local/state}/herdr/plugins/<id>`
      (a relative path is ignored)
- [ ] a missing, empty, broken or mistyped `config.json` gives the defaults and a logged reason
- [ ] `records_dir` moves only the records; `observed.json` and the log stay in the state directory
- [ ] `claude_config_dir` defaults to `$CLAUDE_CONFIG_DIR`, then `~/.claude`
- [ ] `context_window_by_model` is a map of model id prefix to a positive integer; other
      shapes are ignored with a logged reason
- [ ] `prepare_command`, `prepare_prompt` and `prepare_timeout_seconds` are read with their
      defaults; a set `prepare_prompt` takes precedence over `prepare_command`

### records
- [ ] a record is written under its UUID, directories 0700 and files 0600
- [ ] a non-UUID session_id is rejected (path separators, `..`, empty)
- [ ] writes are atomic renames; a crash midway keeps the old record
- [ ] broken JSON is moved to `records/broken/` and reported as a broken record
- [ ] an unknown `schema_version` is neither read, modified nor deleted
- [ ] a record in `parking` is never overwritten (a second park of the same UUID)
- [ ] resumed records move to `resumed/` and are deleted after the retention (boundary ±1 s)
- [ ] a note with newlines and control characters round-trips unchanged
- [ ] moving `pane_id` keeps the old ID in `pane_id_history`

### argv
- [ ] the executable and `--resume` / `-r` / `--continue` / `-c` / `--session-id` /
      `--name` / `-n` / `--fork-session` with their values are removed; other flags
      (`--effort medium`, `--model x`, `--permission-mode auto`) keep their order
- [ ] both `--resume=<id>` and `-r <id>` are removed
- [ ] a value-taking flag at the end without its value does not crash

### herdr_api
- [ ] `HERDR_BIN_PATH` is used when set, otherwise `herdr` on `PATH`
- [ ] non-JSON output, an `error` reply and a non-zero exit are distinct exceptions
- [ ] replies missing keys (`agent_session`, `foreground_processes`) come back as None without crashing
- [ ] `events.subscribe` waits for the first reply, then yields events, and ends on EOF
- [ ] the subscription list is `pane.agent_detected` without a pane plus one
      `pane.agent_status_changed` per given Claude pane
- [ ] an `error` reply to the subscription is an exception, not an empty stream
- [ ] every command has a timeout and a timeout is an exception
- [ ] the shell-only check is `pid == shell_pid` for the single foreground process,
      whatever its name (`-zsh`, `zsh`, `bash`)

### transcript
- [ ] the transcript of a UUID is found by globbing `<claude_config_dir>/projects/*/<uuid>.jsonl`;
      none or several give no result
- [ ] the tail read never loads more than the cap and handles a line split at the cap
- [ ] the result is cached by mtime and size and re-read when either changes
- [ ] the context tokens are the sum of `input_tokens`, `cache_creation_input_tokens` and
      `cache_read_input_tokens` of the last `assistant` line with `message.usage` after
      the last `compact_boundary`
- [ ] a session is compacted when the last `compact_boundary` has no assistant usage after
      it; a following `user` line with `isCompactSummary: true` does not change that
- [ ] the compacted age comes from the boundary's `timestamp`
- [ ] the window size comes from `context_window_by_model` by model id prefix, else from
      the statusline file `context-windows.json` by session id, else is unknown
- [ ] the percentage is truncated (36890 / 200000 → 18) and absent when the window is unknown
- [ ] a missing, unreadable or empty transcript gives an empty ctx
- [ ] the focus tag `<compact-focus>...</compact-focus>` is taken from the assistant text
      after the line whose user text equals the sent prompt; none gives an empty focus
- [ ] a new `compact_boundary` after a given time is detected

### inventory
- [ ] only `agent == "claude"` panes become rows; the dashboard's own pane (`HERDR_PANE_ID`) is excluded
- [ ] a row has place (workspace / tab / pane and labels), name (`terminal_title_stripped`),
      cwd, status and the `agent_session` UUID
- [ ] the Claude process is the foreground group leader (`pid == foreground_process_group_id`)
- [ ] its argv comes from `process-info`, else from `/proc/<pid>/cmdline` (NUL-separated),
      else is empty
- [ ] its running version is the basename of `readlink /proc/<pid>/exe` when `/proc`
      exists, else `process-info`'s `name` when it looks like a version, else unknown
- [ ] RSS is read in KiB from `VmRSS` in `/proc/<pid>/status` when `/proc` exists, else
      from `ps -o rss=`, and the row survives when both fail
- [ ] RSS is the sum over every foreground pid, with the Claude-only value kept
- [ ] the current version is the basename of the `realpath` of `argv[0]` when it is a path,
      else of `claude_command` found on `PATH`, else of `~/.local/bin/claude`; `old` when it
      differs from the running version, no badge when equal or either is unknown
- [ ] ctx shows `37k 18%`, `37k`, or `compacted 2h`, and is empty without a transcript
- [ ] a record whose `pane_id` hosts a Claude with the same `agent_session.value` becomes
      `resumed` and its label is restored (resumed by hand)
- [ ] a record whose UUID runs in another pane becomes `resumed`, `pane_id` moves, the old
      ID goes to `pane_id_history`, and the original pane's label is restored
- [ ] a different UUID in the record's pane shows "another session is running here" and keeps the record
- [ ] a pane with a record is `parked`; a record without a pane is a "(no pane)" row
- [ ] Codex and other agents are counted for the footer
- [ ] control characters in `terminal_title_stripped` are dropped and the name is cut to
      the column (CJK counts double width)

### idle (injectable clock)
- [ ] a row seen for the first time gets `since = now` and `lower_bound = true`
- [ ] a changed `state_change_seq` updates `since` and clears `lower_bound`
- [ ] tracking of a vanished pane is dropped at the next save
- [ ] `observed.json` is written by atomic rename and a broken file starts empty
- [ ] idle times render as `12m`, `3h05m`, `2d`, with `≥` for lower bounds
- [ ] a change delivered by an event and by polling does not count twice on one row

### park (fake herdr)
- [ ] only `idle` and `done` panes can be parked; `working` / `blocked` / `unknown` are refused with a reason
- [ ] a Claude pane without `agent_session` is refused with "integration required"
- [ ] a pane with a half-typed line is refused and no `/exit` is sent
- [ ] the input box is read from `agent read --format ansi`: `❯` alone and `❯` followed only
      by dim (`ESC[2m`) placeholder text are empty; any other text is a draft; no `❯` line
      between rules is "unknown" and refused
- [ ] the park confirmation always carries the warning about lost background tasks
- [ ] the record is written before `/exit` is sent (order of the fake herdr calls)
- [ ] `/exit` is sent with `agent prompt <P> "/exit"`
- [ ] the shell is awaited by polling `pane get`; then the label becomes `💤 <name>` and
      `label_before` keeps the previous label
- [ ] `layout_hint` (sibling pane id or `null` for a subtree, `first` / `second`, direction,
      ratio, boolean path) from `layout.export` is stored before the park, whatever
      `on_park` is
- [ ] by default (`on_park` unset) the pane is not closed
- [ ] with `on_park = close`, `pane close <P>` is called after the shell is back and
      `parked_mode` is `"close"`
- [ ] with `on_park = close`, the last pane of a tab and a pane with something other than
      the shell (`pid != shell_pid`) in the foreground are not closed; `parked_mode` is
      `"keep"` and a reason is returned
- [ ] a timeout gives `park_failed` and the pane is untouched
- [ ] `agent_blocked` from `agent prompt` is a refusal: no `park_failed`, the record is removed
- [ ] the note is stored; an empty note is `null`
- [ ] the context numbers at park time are stored in `context_at_park`
- [ ] bulk park targets only idle/done rows at or above the threshold, including `≥` rows,
      continues after one failure, and reports the results
- [ ] the label format is configurable, cut at 80 characters, and free of control characters

### compact (fake herdr, fake transcript)
- [ ] `c` on `idle` / `done` with an empty input box sends `prepare_command` with `agent prompt`;
      other states and a half-typed line are refused
- [ ] with `prepare_prompt` set, that text is sent instead of `prepare_command`
- [ ] the flow waits with `agent wait --until idle --timeout <prepare_timeout_seconds>`
- [ ] the focus tag is taken from the assistant text after the sent prompt
- [ ] the confirmation shows the report summary and the focus, and the focus can be edited
- [ ] `/compact <focus>` is sent as one line (newlines become spaces); an empty focus sends `/compact`
- [ ] the flow completes when a new `compact_boundary` appears; the row turns `compacted`
- [ ] a preparation that becomes `blocked` stops the flow with a message to go to the pane
- [ ] `c` again with a focus tag already present continues from the focus extraction
- [ ] no focus tag gives an empty focus in the confirmation
- [ ] a boundary that does not appear within `compact_timeout_seconds` gives `compact_failed`
- [ ] `C` asks for the note first, runs the compact flow, then the park procedure; a failed
      compact does not park

### resume (fake herdr)
- [ ] with the pane present and the shell alone in the foreground,
      `agent start <name> --kind claude --pane <P> --timeout <ms> -- --resume <UUID> <flags>` is called
- [ ] `<name>` matches `[a-z][a-z0-9_-]{0,31}` and derives from the UUID
- [ ] a pane cwd different from the record's runs `pane run <P> "cd <quoted>"` first
- [ ] the note is printed with `pane run <P> "printf ..."` before the resume; a failure does not stop it
- [ ] after success, a matching `agent_session.value` restores the label and moves the record to `resumed/`
- [ ] a mismatch gives `resume_failed` with both IDs in `error`
- [ ] `agent_not_ready` gives `resume_pending` and leaves the label
- [ ] a retry from `resume_pending` with a matching Claude already running only restores the
      label and moves the record
- [ ] a timeout gives `resume_failed` with the last 10 lines of `pane read` as the reason
- [ ] a pane with another command in the foreground is refused
- [ ] only with `send_note_as_prompt = true` is `agent prompt <P> <note>` sent after `agent wait --until idle`
- [ ] before `r`, a matching UUID running elsewhere makes the record `resumed` without starting a second process
- [ ] swap parks then resumes in the same pane, and a refused park does not resume
- [ ] swap asks for confirmation when the running version equals the current one

### recreate (fake herdr)
- [ ] with a `second`-position hint and its sibling pane present, `pane split <sibling> --direction <dir> --cwd <cwd> --no-focus`, then `layout.set_split_ratio` with the recorded path and ratio
- [ ] with a `first`-position hint, the same split followed by `pane.swap {source_pane_id: <new>, target_pane_id: <sibling>}` before the ratio is set
- [ ] with a subtree sibling (`null`) or a missing sibling but the tab present, `pane split --direction right --cwd <cwd> --no-focus` on a pane of that tab
- [ ] without the tab but with the workspace, `tab create --workspace <W> --cwd <cwd> --label <tab_label> --no-focus`
- [ ] without the workspace, after confirmation, `workspace create --cwd <cwd> --label <label> --no-focus`
- [ ] without the cwd, stop with a reason
- [ ] the new pane ID is written and the old one goes to `pane_id_history`

### dashboard (PTY, fake herdr, injectable clock)
- [ ] the list is drawn at start and column widths fit the terminal width
- [ ] j/k and the arrows move the selection and stop at the ends
- [ ] `s` parks through the confirmation and the note input, and the list refreshes
- [ ] `s` on a `working` row shows a reason and does nothing
- [ ] `c` runs the compact flow with its confirmation; `C` asks for the note first
- [ ] `r` shows the full note and the resume command, Enter resumes, Esc returns
- [ ] `R` parks and resumes in one go, with the same-version confirmation
- [ ] `g` moves to the pane and closes the dashboard
- [ ] `S` edits the threshold, lists the targets with exclusion reasons, takes one note, confirms, then parks
- [ ] `n` rewrites the note
- [ ] `x` deletes the record after confirmation and never touches the transcript
- [ ] `/` filters by name, cwd and label
- [ ] polling updates status, RSS and ctx, and idle time advances
- [ ] a dropped event subscription keeps polling and shows "events: off" in the footer
- [ ] q, SIGTERM, SIGHUP and EOF exit and restore the TTY
- [ ] SIGWINCH redraws
- [ ] an unexpected exception is logged to `dashboard.log` before exit
- [ ] a second dashboard at the same time does not corrupt `observed.json`

### cli
- [ ] `dashboard` starts the pane process
- [ ] `open` calls `plugin pane open --plugin <id> --entrypoint dashboard --placement overlay`,
      `open-tab` calls `--placement tab --workspace <HERDR_WORKSPACE_ID>`
- [ ] `list` prints the rows as JSON (with the Claude-only RSS)
- [ ] `park <pane>`, `compact <pane>` and `resume <uuid>` run the same procedures without
      the dashboard; failures exit 1 with a message
- [ ] the manifest declares the `dashboard` pane and the `open` / `open-tab` actions, and
      `herdr plugin link` of the clone lists both (Mac)

### skill
- [ ] `skills/prepare-compact/SKILL.md` exists (English): save state worth keeping to memory
      or the relevant files; check and report the commit and push state; clean up temporary
      processes and files; check that nothing that would hurt to lose is left; end with one
      line `<compact-focus>...</compact-focus>` for `/compact`; never run `/compact` itself
- [ ] the README explains copying the skill for public users and recommends a
      `Compact Instructions` section in `CLAUDE.md`

### integration (devcon-herdr)
- [ ] `devcon-herdr plugins update` locks this plugin's latest release
- [ ] the locked commit is installed on the Mac and in a container, and nothing happens when current
- [ ] a locally linked plugin is reported and left alone
- [ ] the skill mirror carries `prepare-compact` to the Mac and the containers

### real devices
- [ ] Mac local: park an idle Claude → the label appears → `r` resumes in the same pane and
      `agent_session` is the same UUID
- [ ] Mac local: close the parked pane, then `r` → recreated in the same tab and resumed
- [ ] Mac local: `on_park = close` → the pane closes → `r` recreates it next to the old neighbour
- [ ] Mac local: `R` brings an old Claude up on the new version and `old` disappears
- [ ] Mac local: a folder with a trust dialog gives `resume_pending`, and `r` after answering completes
- [ ] Mac local: `S` parks only sessions idle for 60 minutes or more, in order
- [ ] Mac local: `c` prepares, shows the focus, compacts, and the row turns `compacted`
- [ ] Mac local: `C` compacts then parks, and the resumed session starts from the summary
- [ ] Mac local: ctx matches the statusline (tokens and percentage) for a haiku session and
      an Opus session with the window configured
- [ ] WSL2 thin client + container: the dashboard lists only the server-side (container)
      Claudes, parks and resumes; records are in the container's state directory
- [ ] after a Herdr server restart (throwaway session): a parked pane keeps its record
      and label and `r` resumes it in the same pane ID (spike 0-1, 0-2)

## Open items

See "Open items" in `DESIGN.md`: everything unverified is a spike above, none of it a
decision still pending.
