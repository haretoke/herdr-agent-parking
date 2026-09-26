"""The dashboard's rows: every Claude pane of this Herdr server with what the plugin
knows about it (process, memory, version, context, park record)."""

from dataclasses import dataclass
from typing import Optional


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
