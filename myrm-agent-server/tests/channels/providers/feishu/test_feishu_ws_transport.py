"""Tests for Feishu WebSocket transport layer."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.providers.feishu.ws_transport import (
    FeishuWSTransport,
    _deep_vars,
)

# ── _sdk_event_to_dict ──────────────────────────────────────────


class TestSdkEventToDict:
    """Verify 3-layer conversion: dict passthrough → raw_body → attr extraction."""

    def test_dict_passthrough(self) -> None:
        data = {"header": {"event_type": "im.message.receive_v1"}, "event": {"k": "v"}}
        result = FeishuWSTransport._sdk_event_to_dict(data, "im.message.receive_v1")
        assert result is data

    def test_raw_body_str(self) -> None:
        body = {"header": {"event_type": "im.message.receive_v1"}, "event": {"msg": "hi"}}
        obj = SimpleNamespace(raw_body=json.dumps(body))
        result = FeishuWSTransport._sdk_event_to_dict(obj, "im.message.receive_v1")
        assert result == body

    def test_raw_body_bytes(self) -> None:
        body = {"header": {"event_type": "test"}, "event": {"key": 1}}
        obj = SimpleNamespace(raw_body=json.dumps(body).encode())
        result = FeishuWSTransport._sdk_event_to_dict(obj, "test")
        assert result == body

    def test_raw_body_invalid_json_falls_through(self) -> None:
        obj = SimpleNamespace(
            raw_body="not-json",
            header=SimpleNamespace(
                event_id="e1",
                event_type="im.message.receive_v1",
                create_time="123",
                token="tok",
            ),
            event={"sender_id": "u1"},
        )
        result = FeishuWSTransport._sdk_event_to_dict(obj, "im.message.receive_v1")
        assert result is not None
        assert result["event"] == {"sender_id": "u1"}
        assert result["header"]["event_id"] == "e1"

    def test_attr_extraction_with_header(self) -> None:
        header = SimpleNamespace(
            event_id="ev123",
            event_type="im.message.receive_v1",
            create_time="1700000000",
            token="t",
        )
        event = SimpleNamespace(message_id="m1", sender_id="u1")
        obj = SimpleNamespace(header=header, event=event)
        result = FeishuWSTransport._sdk_event_to_dict(obj, "im.message.receive_v1")
        assert result is not None
        assert result["header"]["event_id"] == "ev123"
        assert result["event"]["message_id"] == "m1"

    def test_no_header_uses_fallback(self) -> None:
        obj = SimpleNamespace(event={"data": "val"})
        result = FeishuWSTransport._sdk_event_to_dict(obj, "card.action.trigger")
        assert result is not None
        assert result["header"]["event_type"] == "card.action.trigger"

    def test_empty_event_returns_none(self) -> None:
        obj = SimpleNamespace(
            header=SimpleNamespace(
                event_id="e1",
                event_type="test",
                create_time="",
                token="",
            )
        )
        result = FeishuWSTransport._sdk_event_to_dict(obj, "test")
        assert result is None

    def test_event_without_dict_returns_none(self) -> None:
        obj = SimpleNamespace(
            header=SimpleNamespace(
                event_id="e1",
                event_type="test",
                create_time="",
                token="",
            ),
            event=42,
        )
        result = FeishuWSTransport._sdk_event_to_dict(obj, "test")
        assert result is None


# ── _deep_vars ──────────────────────────────────────────────────


class TestDeepVars:
    def test_flat_object(self) -> None:
        obj = SimpleNamespace(name="alice", age=30)
        assert _deep_vars(obj) == {"name": "alice", "age": 30}

    def test_nested_object(self) -> None:
        inner = SimpleNamespace(city="NYC")
        outer = SimpleNamespace(info=inner, score=10)
        result = _deep_vars(outer)
        assert result == {"info": {"city": "NYC"}, "score": 10}

    def test_list_of_objects(self) -> None:
        items = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        obj = SimpleNamespace(items=items)
        result = _deep_vars(obj)
        assert result == {"items": [{"id": 1}, {"id": 2}]}

    def test_skips_private_attrs(self) -> None:
        obj = SimpleNamespace(_internal="secret", public="visible")
        assert _deep_vars(obj) == {"public": "visible"}

    def test_mixed_list(self) -> None:
        obj = SimpleNamespace(data=[SimpleNamespace(x=1), "plain", 42])
        result = _deep_vars(obj)
        assert result == {"data": [{"x": 1}, "plain", 42]}


# ── FeishuWSTransport lifecycle ─────────────────────────────────


class TestTransportLifecycle:
    def test_initial_state(self) -> None:
        transport = FeishuWSTransport("app_id", "app_secret")
        assert not transport.is_running
        assert transport._ws_thread is None

    @pytest.mark.asyncio
    async def test_start_raises_without_sdk(self) -> None:
        transport = FeishuWSTransport("app_id", "app_secret")
        callback = AsyncMock()
        with (
            patch(
                "app.channels.providers.feishu.ws_transport.SDK_AVAILABLE",
                False,
            ),
            pytest.raises(RuntimeError, match="lark-oapi SDK is required"),
        ):
            await transport.start(on_event=callback)

    @pytest.mark.asyncio
    async def test_stop_sets_event(self) -> None:
        transport = FeishuWSTransport("app_id", "app_secret")
        transport._running = True
        await transport.stop()
        assert not transport._running
        assert transport._stop_event.is_set()


# ── _dispatch_event ─────────────────────────────────────────────


class TestDispatchEvent:
    def test_dispatch_schedules_coroutine(self) -> None:
        transport = FeishuWSTransport("app_id", "app_secret")
        transport._loop = MagicMock()
        transport._on_event = AsyncMock()

        mock_fut = MagicMock()
        with patch("asyncio.run_coroutine_threadsafe", return_value=mock_fut) as mock_rcts:
            transport._dispatch_event({"header": {}, "event": {}})
            mock_rcts.assert_called_once()
            mock_fut.add_done_callback.assert_called_once_with(
                FeishuWSTransport._log_dispatch_error,
            )

    def test_dispatch_closes_coroutine_on_runtime_error(self) -> None:
        transport = FeishuWSTransport("app_id", "app_secret")
        transport._loop = MagicMock()
        mock_coro = MagicMock()
        transport._on_event = MagicMock(return_value=mock_coro)

        with patch("asyncio.run_coroutine_threadsafe", side_effect=RuntimeError("loop closed")):
            transport._dispatch_event({"header": {}, "event": {}})
            mock_coro.close.assert_called_once()

    def test_dispatch_noop_without_loop(self) -> None:
        transport = FeishuWSTransport("app_id", "app_secret")
        transport._on_event = AsyncMock()
        with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
            transport._dispatch_event({"header": {}, "event": {}})
            mock_rcts.assert_not_called()

    def test_dispatch_noop_without_callback(self) -> None:
        transport = FeishuWSTransport("app_id", "app_secret")
        transport._loop = MagicMock()
        with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
            transport._dispatch_event({"header": {}, "event": {}})
            mock_rcts.assert_not_called()


# ── Sync callbacks guard ────────────────────────────────────────


class TestSyncCallbackGuards:
    def test_on_message_sync_skips_when_not_running(self) -> None:
        transport = FeishuWSTransport("app_id", "app_secret")
        transport._running = False
        transport._loop = MagicMock()
        transport._on_event = AsyncMock()
        with patch.object(transport, "_dispatch_event") as mock_disp:
            transport._on_message_sync({"header": {}, "event": {"k": "v"}})
            mock_disp.assert_not_called()

    def test_on_card_action_sync_skips_when_not_running(self) -> None:
        transport = FeishuWSTransport("app_id", "app_secret")
        transport._running = False
        transport._loop = MagicMock()
        transport._on_event = AsyncMock()
        with patch.object(transport, "_dispatch_event") as mock_disp:
            transport._on_card_action_sync({"header": {}, "event": {"k": "v"}})
            mock_disp.assert_not_called()

    def test_on_message_sync_dispatches_when_running(self) -> None:
        transport = FeishuWSTransport("app_id", "app_secret")
        transport._running = True
        transport._loop = MagicMock()
        transport._on_event = AsyncMock()
        data = {"header": {"event_type": "im.message.receive_v1"}, "event": {"msg": "hi"}}
        with patch.object(transport, "_dispatch_event") as mock_disp:
            transport._on_message_sync(data)
            mock_disp.assert_called_once_with(data)


# ── _log_dispatch_error ─────────────────────────────────────────


class TestLogDispatchError:
    def test_logs_exception(self) -> None:
        fut: MagicMock = MagicMock()
        fut.exception.return_value = ValueError("boom")
        FeishuWSTransport._log_dispatch_error(fut)

    def test_noop_on_success(self) -> None:
        fut: MagicMock = MagicMock()
        fut.exception.return_value = None
        FeishuWSTransport._log_dispatch_error(fut)


# ── Stop event interrupts sleep ─────────────────────────────────


class TestStopEventInterruptsSleep:
    @pytest.mark.asyncio
    async def test_stop_interrupts_retry_wait(self) -> None:
        """Verify _stop_event.wait() returns immediately when stop() is called."""
        transport = FeishuWSTransport("app_id", "app_secret")
        transport._running = True
        transport._stop_event.clear()

        interrupted = threading.Event()

        def _wait_and_check() -> None:
            transport._stop_event.wait(60.0)
            interrupted.set()

        t = threading.Thread(target=_wait_and_check, daemon=True)
        t.start()

        await transport.stop()
        interrupted.wait(timeout=2.0)
        assert interrupted.is_set(), "stop() did not interrupt _stop_event.wait()"
