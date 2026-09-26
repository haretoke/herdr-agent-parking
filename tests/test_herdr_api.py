import unittest

from agent_parking import herdr_api
from tests.fake_herdr import Error, FakeHerdr


class CallTest(unittest.TestCase):
    def fake(self, script):
        fake = FakeHerdr(script)
        self.addCleanup(fake.close)
        return fake

    def test_a_call_sends_one_request_line_and_returns_the_result(self):
        fake = self.fake({"pane.get": {"type": "pane_info", "pane": {"pane_id": "w1:p1"}}})
        herdr = herdr_api.Herdr(fake.path)
        result = herdr.call("pane.get", {"pane_id": "w1:p1"})
        self.assertEqual(result, {"type": "pane_info", "pane": {"pane_id": "w1:p1"}})
        self.assertEqual(fake.requests[0]["method"], "pane.get")
        self.assertEqual(fake.requests[0]["params"], {"pane_id": "w1:p1"})
        self.assertTrue(fake.requests[0]["id"])

    def test_each_call_uses_its_own_connection(self):
        fake = self.fake({"agent.list": {"type": "agent_list", "agents": []}})
        herdr = herdr_api.Herdr(fake.path)
        herdr.call("agent.list", {})
        herdr.call("agent.list", {})
        self.assertEqual(fake.connections, 2)

    def test_the_socket_comes_from_the_environment_and_its_absence_is_named(self):
        fake = self.fake({"agent.list": {"agents": []}})
        herdr = herdr_api.Herdr.from_environ({"HERDR_SOCKET_PATH": fake.path})
        self.assertEqual(herdr.call("agent.list", {}), {"agents": []})
        for environ in ({}, {"HERDR_SOCKET_PATH": ""}):
            with self.subTest(environ=environ):
                with self.assertRaisesRegex(herdr_api.HerdrError, "not running inside Herdr") as raised:
                    herdr_api.Herdr.from_environ(environ)
                self.assertEqual(raised.exception.code, "not_in_herdr")


class ErrorTest(unittest.TestCase):
    def fake(self, script):
        fake = FakeHerdr(script)
        self.addCleanup(fake.close)
        return fake

    def raised(self, herdr, method="pane.get"):
        with self.assertRaises(herdr_api.HerdrError) as raised:
            herdr.call(method, {"pane_id": "w1:p1"})
        return raised.exception

    def test_an_error_reply_keeps_its_code_and_message(self):
        fake = self.fake({"pane.get": Error("pane_not_found", "pane w1:p1 not found")})
        error = self.raised(herdr_api.Herdr(fake.path))
        self.assertEqual(error.code, "pane_not_found")
        self.assertIn("pane w1:p1 not found", str(error))

    def test_a_reply_that_is_not_json_is_its_own_error(self):
        def garbage(fake, connection, reader, request):
            connection.sendall(b"not json\n")

        error = self.raised(herdr_api.Herdr(self.fake({"pane.get": garbage}).path))
        self.assertEqual(error.code, "invalid_reply")

    def test_a_connection_closed_without_a_reply_is_its_own_error(self):
        def hang_up(fake, connection, reader, request):
            pass

        error = self.raised(herdr_api.Herdr(self.fake({"pane.get": hang_up}).path))
        self.assertEqual(error.code, "closed")

    def test_an_unreachable_socket_is_its_own_error(self):
        fake = self.fake({})
        path = fake.path
        fake.close()
        error = self.raised(herdr_api.Herdr(path))
        self.assertEqual(error.code, "unreachable")


if __name__ == "__main__":
    unittest.main()
