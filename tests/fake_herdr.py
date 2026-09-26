"""A scripted Herdr socket server for tests.

Every connection is read one request line at a time and answered by the script
entry for its method: a dict (the result), an `Error`, or a callable
`(fake, connection, reader, request)` that answers itself (streams, delays). A
method without an entry gets an `fake_unexpected` error so a test fails loudly
instead of hanging.
"""

import json
import socket
import tempfile
import threading
from pathlib import Path


class Error:
    def __init__(self, code, message=None):
        self.code = code
        self.message = message or code


class FakeHerdr:
    def __init__(self, script=None):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "herdr.sock")
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen(16)
        self.script = dict(script or {})
        self.requests = []
        self.connections = 0
        self.threads = []
        self.closed = False
        self.acceptor = threading.Thread(target=self.accept_loop, daemon=True)
        self.acceptor.start()

    def accept_loop(self):
        while not self.closed:
            try:
                connection, _ = self.server.accept()
            except OSError:
                return
            self.connections += 1
            thread = threading.Thread(target=self.serve, args=(connection,), daemon=True)
            self.threads.append(thread)
            thread.start()

    def serve(self, connection):
        with connection:
            reader = connection.makefile("rb")
            line = reader.readline()
            if not line:
                return
            request = json.loads(line)
            self.requests.append(request)
            entry = self.script.get(request["method"])
            if callable(entry):
                entry(self, connection, reader, request)
            elif isinstance(entry, Error):
                self.reply(connection, request, error={"code": entry.code, "message": entry.message})
            elif entry is None:
                self.reply(connection, request, error={"code": "fake_unexpected",
                                                       "message": "no script for " + request["method"]})
            else:
                self.reply(connection, request, result=entry)

    def reply(self, connection, request, result=None, error=None):
        body = {"id": request["id"]}
        if error is not None:
            body["error"] = error
        else:
            body["result"] = result if result is not None else {"type": "ok"}
        self.send_line(connection, body)

    @staticmethod
    def send_line(connection, body):
        try:
            connection.sendall((json.dumps(body) + "\n").encode())
        except OSError:
            pass

    def methods(self):
        return [r["method"] for r in self.requests]

    def close(self):
        self.closed = True
        self.server.close()
        for thread in self.threads:
            thread.join(timeout=5)
        self.acceptor.join(timeout=5)
        self.directory.cleanup()
