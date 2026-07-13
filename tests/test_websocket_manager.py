import asyncio

import pytest

from services.websocket_manager import ConnectionManager


class _FakeWebSocket:
    def __init__(self, fail=False):
        self.accepted = False
        self.sent = []
        self.fail = fail

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        if self.fail:
            raise RuntimeError("connection closed")
        self.sent.append(message)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestConnectionManager:
    def test_connect_accepts_and_tracks(self):
        mgr = ConnectionManager()
        ws = _FakeWebSocket()
        _run(mgr.connect(ws, "alice"))
        assert ws.accepted is True
        assert mgr.active_connections["alice"] == [ws]

    def test_multiple_connections_same_user(self):
        mgr = ConnectionManager()
        ws1, ws2 = _FakeWebSocket(), _FakeWebSocket()
        _run(mgr.connect(ws1, "alice"))
        _run(mgr.connect(ws2, "alice"))
        assert mgr.active_connections["alice"] == [ws1, ws2]

    def test_disconnect_removes_socket_but_keeps_user(self):
        mgr = ConnectionManager()
        ws1, ws2 = _FakeWebSocket(), _FakeWebSocket()
        _run(mgr.connect(ws1, "alice"))
        _run(mgr.connect(ws2, "alice"))
        assert mgr.disconnect(ws1, "alice") is False
        assert mgr.active_connections["alice"] == [ws2]

    def test_disconnect_last_socket_removes_user(self):
        mgr = ConnectionManager()
        ws = _FakeWebSocket()
        _run(mgr.connect(ws, "alice"))
        assert mgr.disconnect(ws, "alice") is True
        assert "alice" not in mgr.active_connections

    def test_disconnect_unknown_user(self):
        mgr = ConnectionManager()
        assert mgr.disconnect(_FakeWebSocket(), "ghost") is False

    def test_broadcast_sends_to_all(self):
        mgr = ConnectionManager()
        ws1, ws2 = _FakeWebSocket(), _FakeWebSocket()
        _run(mgr.connect(ws1, "alice"))
        _run(mgr.connect(ws2, "bob"))
        _run(mgr.broadcast({"type": "ping"}))
        assert ws1.sent == [{"type": "ping"}]
        assert ws2.sent == [{"type": "ping"}]

    def test_broadcast_ignores_failing_socket(self):
        mgr = ConnectionManager()
        good, bad = _FakeWebSocket(), _FakeWebSocket(fail=True)
        _run(mgr.connect(good, "alice"))
        _run(mgr.connect(bad, "bob"))
        # should not raise despite bad socket failing
        _run(mgr.broadcast({"type": "ping"}))
        assert good.sent == [{"type": "ping"}]
