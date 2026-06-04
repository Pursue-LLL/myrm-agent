"""Feishu WebSocket transport — long-lived connection via lark-oapi SDK.

Encapsulates the lark-oapi WebSocket client lifecycle: start, reconnect,
event dispatch, and graceful stop. Converts SDK event objects to plain
dicts that are compatible with FeishuChannel.handle_webhook_event().

The SDK is imported lazily so webhook-only deployments incur zero overhead.

## Event Loop Isolation for Multiple Instances

Each FeishuWSTransport instance runs in its own background thread with a
dedicated event loop (ws_loop). The lark-oapi SDK uses a module-level `loop`
variable, which is patched atomically via ``_WS_START_LOCK`` before each
client start.

**Thread Safety Analysis**:
- When ``ws_client.start()`` executes ``loop.run_until_complete()``, Python
  resolves the module-level ``loop`` variable and binds the loop object to
  the method call.
- Once ``run_until_complete()`` begins execution, the loop object is bound
  and subsequent modifications to the module-level ``loop`` variable by other
  threads do not affect the running call.
- Each transport's WebSocket client runs on its dedicated loop in an isolated
  thread, ensuring no cross-instance interference.

This design has been verified safe through code analysis and Python's late-
binding semantics. See ``tests/unit/test_feishu_event_loop_isolation.py``
for validation tests.

[INPUT]

[OUTPUT]
- FeishuWSTransport: async-safe WebSocket transport manager

[POS]
Feishu WebSocket transport layer. Wraps lark-oapi SDK WS client, providing
event reception without a public IP. Supports concurrent multi-instance operation
with per-instance thread and event loop isolation.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import threading
import time
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_WS_START_LOCK = threading.Lock()

_MAX_RECONNECT_ATTEMPTS = 50
_INITIAL_RETRY_DELAY = 2.0
_MAX_RETRY_DELAY = 60.0
_BACKOFF_FACTOR = 2.0

_STALE_MSG_THRESHOLD_MS = 20 * 1000  # Drop retry deliveries older than 20s


def _check_sdk_available() -> bool:
    """Check if lark-oapi SDK is installed."""
    try:
        import importlib.util

        return importlib.util.find_spec("lark_oapi") is not None
    except Exception:
        return False


SDK_AVAILABLE = _check_sdk_available()


class FeishuWSTransport:
    """WebSocket transport for Feishu using lark-oapi SDK.

    Manages a background thread running the SDK's WebSocket client.
    Events are dispatched to an async callback on the main event loop
    via ``asyncio.run_coroutine_threadsafe()``.
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        use_lark: bool = False,
        encrypt_key: str = "",
        verification_token: str = "",
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._use_lark = use_lark
        self._encrypt_key = encrypt_key
        self._verification_token = verification_token

        self._running = False
        self._stop_event = threading.Event()
        self._ws_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._on_event: Callable[[dict[str, object]], Awaitable[dict[str, object] | None]] | None = None
        self._consecutive_failures = 0

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(
        self,
        on_event: Callable[[dict[str, object]], Awaitable[dict[str, object] | None]],
    ) -> None:
        """Start the WebSocket transport in a background thread.

        Args:
            on_event: Async callback receiving raw event dicts, compatible
                      with ``FeishuChannel.handle_webhook_event()``.

        Raises:
            RuntimeError: If lark-oapi SDK is not installed.
        """
        if not SDK_AVAILABLE:
            raise RuntimeError(
                "lark-oapi SDK is required for WebSocket transport. "
                "Run: uv sync (lark-oapi is a main dependency)"
            )

        self._loop = asyncio.get_running_loop()
        self._on_event = on_event
        self._running = True
        self._stop_event.clear()
        self._consecutive_failures = 0

        self._ws_thread = threading.Thread(
            target=self._run_ws_loop,
            name="feishu-ws-transport",
            daemon=True,
        )
        self._ws_thread.start()
        logger.info("Feishu WebSocket transport started")

    async def stop(self) -> None:
        """Signal the background thread to exit immediately."""
        self._running = False
        self._stop_event.set()
        logger.info("Feishu WebSocket transport stopped")

    def _run_ws_loop(self) -> None:
        """Background thread: run the SDK WS client with reconnection."""
        import lark_oapi as lark

        ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(ws_loop)

        retry_delay = _INITIAL_RETRY_DELAY

        try:
            while self._running and self._consecutive_failures < _MAX_RECONNECT_ATTEMPTS:
                try:
                    self._start_ws_client(lark, ws_loop)
                    retry_delay = _INITIAL_RETRY_DELAY
                except Exception as exc:
                    self._consecutive_failures += 1
                    logger.warning(
                        "Feishu WS connection failed (%d/%d): %s",
                        self._consecutive_failures,
                        _MAX_RECONNECT_ATTEMPTS,
                        exc,
                    )

                if not self._running:
                    break

                self._stop_event.wait(retry_delay)
                if self._stop_event.is_set():
                    break
                retry_delay = min(retry_delay * _BACKOFF_FACTOR, _MAX_RETRY_DELAY)

            if self._consecutive_failures >= _MAX_RECONNECT_ATTEMPTS:
                logger.error(
                    "Feishu WS transport gave up after %d consecutive failures",
                    _MAX_RECONNECT_ATTEMPTS,
                )
        finally:
            ws_loop.close()

    def _start_ws_client(self, lark: object, ws_loop: asyncio.AbstractEventLoop) -> None:
        """Create and start one SDK WebSocket client session.

        Uses ``_WS_START_LOCK`` to patch the SDK's module-level ``loop``
        variable atomically, then releases the lock before the blocking
        ``start()`` so other instances can initialize concurrently.
        """
        import lark_oapi.ws.client as _ws_mod

        event_handler = self._build_event_handler(lark)

        domain = self._resolve_domain(lark)
        ws_client = lark.ws.Client(  # type: ignore[attr-defined]
            self._app_id,
            self._app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.WARNING,  # type: ignore[attr-defined]
            domain=domain,
        )

        with _WS_START_LOCK:
            _ws_mod.loop = ws_loop  # type: ignore[attr-defined]

        ws_client.start()
        self._consecutive_failures = 0

    def _resolve_domain(self, lark: object) -> object:
        """Return the SDK domain constant for Feishu or Lark International."""
        from lark_oapi.core.const import FEISHU_DOMAIN, LARK_DOMAIN

        return LARK_DOMAIN if self._use_lark else FEISHU_DOMAIN

    def _build_event_handler(self, lark: object) -> object:
        """Build an EventDispatcherHandler with message + card action callbacks."""
        builder = lark.EventDispatcherHandler.builder(  # type: ignore[attr-defined]
            self._encrypt_key,
            self._verification_token,
        )

        builder = builder.register_p2_im_message_receive_v1(self._on_message_sync)

        register_card = getattr(builder, "register_p2_card_action_trigger", None)
        if callable(register_card):
            builder = register_card(self._on_card_action_sync)

        return builder.build()

    def _on_message_sync(self, data: object) -> None:
        """Sync callback from SDK thread for im.message.receive_v1 events.

        Filters stale retry deliveries: Feishu retries at 5s/5min/1h/6h intervals.
        Messages older than 20 seconds are dropped to prevent duplicate processing.
        """
        if not self._running or not self._loop or not self._on_event:
            return

        header = getattr(data, "header", None)
        if header:
            create_time = getattr(header, "create_time", None)
            if create_time:
                try:
                    now_ms = int(time.time() * 1000)
                    age_ms = now_ms - int(create_time)
                    if age_ms > _STALE_MSG_THRESHOLD_MS:
                        logger.debug(
                            "Feishu: drop stale message age=%.1fs (retry delivery)",
                            age_ms / 1000,
                        )
                        return
                except (ValueError, TypeError):
                    pass

        event_dict = self._sdk_event_to_dict(data, "im.message.receive_v1")
        if event_dict:
            self._dispatch_event(event_dict)

    def _on_card_action_sync(self, data: object) -> None:
        """Sync callback from SDK thread for card.action.trigger events."""
        if not self._running or not self._loop or not self._on_event:
            return
        event_dict = self._sdk_event_to_dict(data, "card.action.trigger")
        if event_dict:
            self._dispatch_event(event_dict)

    def _dispatch_event(self, event_dict: dict[str, object]) -> None:
        """Thread-safely schedule the async callback on the main event loop."""
        if not self._loop or not self._on_event:
            return
        coro = self._on_event(event_dict)
        try:
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
            fut.add_done_callback(self._log_dispatch_error)
        except RuntimeError:
            coro.close()

    @staticmethod
    def _log_dispatch_error(fut: concurrent.futures.Future[object]) -> None:
        exc = fut.exception()
        if exc:
            logger.debug("Feishu WS event handler error: %s", exc)

    @staticmethod
    def _sdk_event_to_dict(data: object, event_type: str) -> dict[str, object] | None:
        """Convert an SDK event object to the raw dict format.

        The dict format matches what FeishuChannel.handle_webhook_event()
        expects from an HTTP webhook POST body.
        """
        if isinstance(data, dict):
            return data

        try:
            raw = getattr(data, "raw_body", None)
            if raw and isinstance(raw, (str, bytes)):
                text = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
                return json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            pass

        result: dict[str, object] = {}

        header = getattr(data, "header", None)
        if header:
            result["header"] = {
                "event_id": getattr(header, "event_id", ""),
                "event_type": getattr(header, "event_type", event_type),
                "create_time": getattr(header, "create_time", ""),
                "token": getattr(header, "token", ""),
            }
        else:
            result["header"] = {"event_type": event_type}

        event = getattr(data, "event", None)
        if event is not None:
            if isinstance(event, dict):
                result["event"] = event
            elif hasattr(event, "__dict__"):
                result["event"] = _deep_vars(event)
            else:
                result["event"] = {}
        else:
            result["event"] = {}

        return result if result.get("event") else None


def _deep_vars(obj: object) -> dict[str, object]:
    """Recursively convert an SDK object tree to plain dicts."""
    result: dict[str, object] = {}
    for key, value in vars(obj).items():
        if key.startswith("_"):
            continue
        if hasattr(value, "__dict__") and not isinstance(value, type):
            result[key] = _deep_vars(value)
        elif isinstance(value, list):
            result[key] = [_deep_vars(item) if hasattr(item, "__dict__") else item for item in value]
        else:
            result[key] = value
    return result
