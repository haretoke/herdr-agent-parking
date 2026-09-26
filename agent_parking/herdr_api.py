"""Herdr's socket API: one request per connection, like image-viewer's herdr_api."""

import json
import socket
import uuid
from collections import namedtuple

MAX_LINE_BYTES = 4 * 1024 * 1024


Pane = namedtuple("Pane", "pane_id tab_id workspace_id agent agent_status cwd label title session_id")
ProcessInfo = namedtuple("ProcessInfo", "shell_pid group_id processes")


def pane_from(raw):
    """A pane reply in a fixed shape; absent keys are None."""
    session = raw.get("agent_session")
    return Pane(pane_id=raw.get("pane_id"), tab_id=raw.get("tab_id"),
                workspace_id=raw.get("workspace_id"), agent=raw.get("agent"),
                agent_status=raw.get("agent_status"), cwd=raw.get("cwd"), label=raw.get("label"),
                title=raw.get("terminal_title_stripped"),
                session_id=session.get("value") if isinstance(session, dict) else None)


class HerdrError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class Herdr:
    def __init__(self, socket_path, timeout=10):
        self.socket_path = socket_path
        self.timeout = timeout

    @classmethod
    def from_environ(cls, environ, timeout=10):
        path = environ.get("HERDR_SOCKET_PATH", "")
        if not path:
            raise HerdrError("not running inside Herdr (HERDR_SOCKET_PATH is not set)", "not_in_herdr")
        return cls(path, timeout)

    def call(self, method, params):
        """Send one request on its own connection and return its result.

        Every failure is a HerdrError: Herdr's own code for an error reply, else
        `unreachable`, `closed` or `invalid_reply`."""
        request = {"id": "agent-parking:" + uuid.uuid4().hex, "method": method, "params": params}
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.timeout)
                client.connect(self.socket_path)
                client.sendall(json.dumps(request).encode("utf-8") + b"\n")
                with client.makefile("rb") as reader:
                    line = reader.readline(MAX_LINE_BYTES + 1)
        except OSError as error:
            raise HerdrError("could not reach Herdr for %s: %s" % (method, error), "unreachable") from error
        return parse_reply(method, line)

    def subscribe(self, subscriptions):
        """Open an `events.subscribe` connection; returns once Herdr acknowledged it."""
        request = {"id": "agent-parking:" + uuid.uuid4().hex, "method": "events.subscribe",
                   "params": {"subscriptions": subscriptions}}
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.settimeout(self.timeout)
            client.connect(self.socket_path)
            client.sendall(json.dumps(request).encode("utf-8") + b"\n")
            reader = client.makefile("rb")
            parse_reply("events.subscribe", reader.readline(MAX_LINE_BYTES + 1))
        except OSError as error:
            client.close()
            raise HerdrError("could not subscribe to Herdr events: %s" % error, "unreachable") from error
        except HerdrError:
            client.close()
            raise
        client.settimeout(None)
        return Subscription(client, reader)

    def pane(self, pane_id):
        raw = self.call("pane.get", {"pane_id": pane_id}).get("pane")
        return pane_from(raw) if isinstance(raw, dict) else None

    def process_info(self, pane_id):
        raw = self.call("pane.process_info", {"pane_id": pane_id}).get("process_info") or {}
        return ProcessInfo(shell_pid=raw.get("shell_pid"), group_id=raw.get("foreground_process_group_id"),
                           processes=list(raw.get("foreground_processes") or []))


def parse_reply(method, line):
    """The result of a reply line, or the HerdrError it stands for."""
    if not line:
        raise HerdrError("Herdr closed the connection without answering %s" % method, "closed")
    try:
        reply = json.loads(line)
    except ValueError as error:
        raise HerdrError("Herdr answered %s with invalid JSON" % method, "invalid_reply") from error
    if not isinstance(reply, dict):
        raise HerdrError("Herdr answered %s with invalid JSON" % method, "invalid_reply")
    if "error" in reply:
        details = reply["error"] if isinstance(reply["error"], dict) else {}
        raise HerdrError("Herdr rejected %s: %s" % (method, details.get("message") or details.get("code")),
                         details.get("code"))
    return reply.get("result", {})


class Subscription:
    """The event lines of an `events.subscribe` connection, until Herdr closes it."""

    def __init__(self, client, reader):
        self.client = client
        self.reader = reader
        self.closed = False

    def fileno(self):
        return self.client.fileno()

    def __iter__(self):
        return self

    def __next__(self):
        line = b"" if self.closed else self.reader.readline(MAX_LINE_BYTES + 1)
        if not line:
            self.close()
            raise StopIteration
        return json.loads(line)

    def close(self):
        if not self.closed:
            self.closed = True
            self.reader.close()
            self.client.close()
