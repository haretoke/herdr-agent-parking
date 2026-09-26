import time
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


class ShapeTest(unittest.TestCase):
    def herdr(self, script):
        fake = FakeHerdr(script)
        self.addCleanup(fake.close)
        return herdr_api.Herdr(fake.path)

    def test_a_pane_is_read_into_a_fixed_shape(self):
        pane = {"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1", "agent": "claude",
                "agent_status": "idle", "cwd": "/w", "label": "L", "terminal_title_stripped": "T",
                "agent_session": {"agent": "claude", "kind": "id", "value": "2716af66-e4d8-4950-8185-97da891f78a9"}}
        got = self.herdr({"pane.get": {"type": "pane_info", "pane": pane}}).pane("w1:p1")
        self.assertEqual(got, herdr_api.Pane(pane_id="w1:p1", tab_id="w1:t1", workspace_id="w1",
                                             agent="claude", agent_status="idle", cwd="/w", label="L",
                                             title="T", session_id="2716af66-e4d8-4950-8185-97da891f78a9"))

    def test_missing_keys_come_back_as_none(self):
        for pane in ({"pane_id": "w1:p1"},
                     {"pane_id": "w1:p1", "agent_session": None},
                     {"pane_id": "w1:p1", "agent_session": {"kind": "id"}}):
            with self.subTest(pane=pane):
                got = self.herdr({"pane.get": {"pane": pane}}).pane("w1:p1")
                self.assertEqual((got.pane_id, got.agent, got.session_id, got.label), ("w1:p1", None, None, None))
        self.assertIsNone(self.herdr({"pane.get": {"type": "pane_info"}}).pane("w1:p1"))

    def test_process_info_without_its_keys_is_empty(self):
        info = self.herdr({"pane.process_info": {"process_info": {}}}).process_info("w1:p1")
        self.assertEqual(info, herdr_api.ProcessInfo(shell_pid=None, group_id=None, processes=[]))
        full = {"process_info": {"shell_pid": 5, "foreground_process_group_id": 7,
                                 "foreground_processes": [{"pid": 7, "name": "2.1.283", "argv": ["claude"]},
                                                          {"pid": 9}]}}
        info = self.herdr({"pane.process_info": full}).process_info("w1:p1")
        self.assertEqual((info.shell_pid, info.group_id), (5, 7))
        self.assertEqual(info.processes, [{"pid": 7, "name": "2.1.283", "argv": ["claude"]}, {"pid": 9}])


class SubscribeTest(unittest.TestCase):
    def herdr(self, script):
        fake = FakeHerdr(script)
        self.addCleanup(fake.close)
        return fake, herdr_api.Herdr(fake.path)

    def test_subscribe_waits_for_the_acknowledgement_then_yields_events_until_eof(self):
        events = [{"event": "pane_agent_detected", "data": {"pane_id": "w1:p5", "agent": "claude"}},
                  {"event": "pane.agent_status_changed", "data": {"pane_id": "w1:p5", "agent_status": "idle"}}]

        def stream(fake, connection, reader, request):
            time.sleep(0.2)
            fake.reply(connection, request, result={"type": "subscription_started"})
            for event in events:
                fake.send_line(connection, event)

        fake, herdr = self.herdr({"events.subscribe": stream})
        started = time.monotonic()
        subscription = herdr.subscribe([{"type": "pane.agent_detected"}])
        self.assertGreaterEqual(time.monotonic() - started, 0.2)
        self.assertEqual(list(subscription), events)
        self.assertTrue(subscription.closed)
        self.assertEqual(fake.requests[0]["params"], {"subscriptions": [{"type": "pane.agent_detected"}]})


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
