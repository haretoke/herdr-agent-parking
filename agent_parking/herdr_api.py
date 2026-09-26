"""Herdr's socket API: one request per connection, like image-viewer's herdr_api."""

import json
import socket
import uuid

MAX_LINE_BYTES = 4 * 1024 * 1024


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
