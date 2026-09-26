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
        """Send one request on its own connection and return its result."""
        request = {"id": "agent-parking:" + uuid.uuid4().hex, "method": method, "params": params}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(self.timeout)
            client.connect(self.socket_path)
            client.sendall(json.dumps(request).encode("utf-8") + b"\n")
            with client.makefile("rb") as reader:
                line = reader.readline(MAX_LINE_BYTES + 1)
        return json.loads(line)["result"]
