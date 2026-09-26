"""The dashboard's rows: every Claude pane of this Herdr server with what the plugin
knows about it (process, memory, version, context, park record)."""

import os
import re
from collections import namedtuple
from dataclasses import dataclass
from typing import Optional

from . import display, herdr_api, transcript

VERSION = re.compile(r"\d+\.\d+\.\d+")


@dataclass
class Row:
    pane_id: Optional[str] = None
    tab_id: Optional[str] = None
    workspace_id: Optional[str] = None
    workspace_label: Optional[str] = None
    tab_label: Optional[str] = None
    label: Optional[str] = None
    name: Optional[str] = None
    cwd: Optional[str] = None
    status: Optional[str] = None
    session_id: Optional[str] = None
    rss_kb: Optional[int] = None          # the whole foreground group
    claude_rss_kb: Optional[int] = None   # Claude alone (the JSON output)
    version: Optional[str] = None
    old: bool = False
    ctx: str = ""
    idle: str = ""
    record: Optional[dict] = None         # the park record, for parked sessions


# The dashboard's rows, and how many panes run each other agent (the "codex: n" in the title).
Inventory = namedtuple("Inventory", "rows others")


def claude_panes(panes, own_pane_id):
    """The panes Herdr recognizes as Claude, without the dashboard's own pane."""
    return [p for p in panes if p.agent == "claude" and p.pane_id != own_pane_id]


def row(pane, workspace_labels, tab_labels):
    """The row of a Claude pane, with the labels of its workspace and tab."""
    return Row(pane_id=pane.pane_id, tab_id=pane.tab_id, workspace_id=pane.workspace_id,
               workspace_label=workspace_labels.get(pane.workspace_id),
               tab_label=tab_labels.get(pane.tab_id), label=pane.label, name=pane.title,
               cwd=pane.cwd, status=pane.agent_status, session_id=pane.session_id)


def claude_process(info):
    """Claude's own entry among the pane's foreground processes: the group leader (MCP
    servers and `caffeinate` share its group; spike 0-10)."""
    for process in info.processes:
        if info.group_id is not None and process.get("pid") == info.group_id:
            return process
    return None


def argv_of(process, system):
    """The Claude process's argv: from Herdr (macOS), else `/proc/<pid>/cmdline` (Herdr 0.9.1
    gives none on Linux; spike 0-10), else empty."""
    return process.get("argv") or system.cmdline(process.get("pid")) or []


def running_version(process, system):
    """The version the Claude process runs: on Linux the name of the executable
    `/proc/<pid>/exe` points to, on macOS Herdr's process `name`; None unless it looks
    like a version (`versions/<v>` of the native installer; spike 0-10)."""
    if system.has_proc():
        exe = system.exe(process.get("pid"))
        candidate = os.path.basename(exe) if exe else None
    else:
        candidate = process.get("name")
    return candidate if candidate and VERSION.fullmatch(candidate) else None


def memory(info, system):
    """(RSS of the whole foreground group, RSS of Claude alone) in KiB. Parking frees the
    group: Claude plus its stdio MCP servers and `caffeinate` (spike 0-11)."""
    known = {p.get("pid"): system.rss_kb(p.get("pid")) for p in info.processes}
    values = [v for v in known.values() if v is not None]
    return (sum(values) if values else None, known.get(info.group_id))


def _version_of(executable, system):
    name = os.path.basename(system.realpath(executable)) if executable else None
    return name if name and VERSION.fullmatch(name) else None


def current_version(argv0, settings, system, environ):
    """The version a new `claude` would start: where the running `argv[0]` points now
    when it is a path (macOS), else `claude_command` on `PATH`, else `~/.local/bin/claude`
    (the plugin runs in the Herdr server's environment, whose PATH may lack it)."""
    if argv0 and "/" in argv0:
        return _version_of(argv0, system)
    found = system.which(settings["claude_command"], environ.get("PATH", ""))
    home = environ.get("HOME") or os.path.expanduser("~")
    return _version_of(found, system) or _version_of(os.path.join(home, ".local", "bin", "claude"), system)


def is_old(running, current):
    return running is not None and current is not None and running != current


def ctx_text(summary, window, now):
    """The ctx column: `37k 18%`, `37k` without a known window, `compacted 2h` while no
    reply followed the last compaction, empty when nothing is known."""
    if summary is None:
        return ""
    if summary.compacted:
        if summary.compacted_at is None:
            return "compacted"
        return "compacted " + display.age((now - summary.compacted_at).total_seconds())
    if summary.tokens is None:
        return ""
    share = transcript.percent(summary.tokens, window)
    text = display.tokens(summary.tokens)
    return text if share is None else "%s %d%%" % (text, share)


Decision = namedtuple("Decision", "record kind pane_id restore_label_on")


def reconcile(parked_records, panes):
    """What each park record means now, given the live panes (pure; the caller acts).

    `resumed`: its session runs in a Claude pane (resumed by hand, maybe elsewhere).
    `conflict`: another Claude session occupies its pane; the record stays.
    `parked`: its pane is there without Claude. `no_pane`: its pane is gone."""
    running = {p.session_id: p for p in panes if p.agent == "claude" and p.session_id}
    by_id = {p.pane_id: p for p in panes}
    decisions = []
    for record in parked_records:
        own = by_id.get(record.get("pane_id"))
        host = running.get(record["session_id"])
        if host is not None:
            decision = Decision(record, "resumed", host.pane_id, own.pane_id if own else None)
        elif own is None:
            decision = Decision(record, "no_pane", None, None)
        elif own.agent == "claude":
            decision = Decision(record, "conflict", own.pane_id, None)
        else:
            decision = Decision(record, "parked", own.pane_id, None)
        decisions.append(decision)
    return decisions


def other_agents(panes):
    """How many panes run each agent other than Claude (the footer's "codex: n")."""
    counts = {}
    for p in panes:
        if p.agent and p.agent != "claude":
            counts[p.agent] = counts.get(p.agent, 0) + 1
    return counts


def _labels(rt, method, key, id_key):
    """`{id: label}` from `workspace.list` or `tab.list`; none when Herdr cannot say (the
    labels only help to recognize a row)."""
    try:
        result = rt.herdr.call(method, {})
    except herdr_api.HerdrError:
        return {}
    return {item.get(id_key): item.get("label") for item in result.get(key) or []}


def build(rt, tracker, own_pane_id):
    """The dashboard's rows now: every Claude pane but the dashboard's own."""
    now = rt.clock()
    panes = rt.herdr.panes()
    workspace_labels = _labels(rt, "workspace.list", "workspaces", "workspace_id")
    tab_labels = _labels(rt, "tab.list", "tabs", "tab_id")
    rows = []
    for pane in claude_panes(panes, own_pane_id):
        found = row(pane, workspace_labels, tab_labels)
        _add_process(rt, found)
        found.ctx = _ctx(rt, found.session_id, now)
        rows.append(found)
    return Inventory(rows, other_agents(panes))


def _add_process(rt, found):
    """Memory and version from the pane's foreground processes (none when the pane went
    away since the list was read)."""
    try:
        info = rt.herdr.process_info(found.pane_id)
    except herdr_api.HerdrError:
        return
    found.rss_kb, found.claude_rss_kb = memory(info, rt.system)
    process = claude_process(info)
    if process is None:
        return
    found.version = running_version(process, rt.system)
    argv0 = (argv_of(process, rt.system) or [None])[0]
    found.old = is_old(found.version, current_version(argv0, rt.settings, rt.system, rt.environ))


def _ctx(rt, session_id, now):
    summary = rt.summary_for(session_id) if session_id else None
    if summary is None:
        return ""
    window = transcript.window_size(summary.model, session_id, rt.settings["context_window_by_model"],
                                    rt.statusline_windows)
    return ctx_text(summary, window, now)
