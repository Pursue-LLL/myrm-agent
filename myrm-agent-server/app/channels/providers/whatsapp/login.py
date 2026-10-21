"""WhatsApp async login: QR-code pairing events streamed to the frontend.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class; supplies the event emitter, status and connection state)
- channels.protocols.async_login::LoginEvent, LoginMethod, LoginState, LoginStatus (POS: async login protocol value types)

[OUTPUT]
- WhatsAppLoginMixin: start_login yields the generating / waiting-for-scan / success / failed / timeout LoginEvent stream for the SSE login endpoint

[POS]
Login half of WhatsAppChannel. The host owns the pairing state the bridge reports (QR string, connection); the mixin renders each QR as a PNG and adapts the host's qr_code / connection_change events to the AsyncLoginProtocol stream.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from collections.abc import AsyncGenerator

from app.channels.core.base import BaseChannel
from app.channels.protocols.async_login import LoginEvent, LoginMethod, LoginState, LoginStatus
from app.channels.types import ChannelStatus

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({LoginStatus.SUCCESS, LoginStatus.FAILED, LoginStatus.TIMEOUT})


def _qr_png_base64(qr_text: str) -> str | None:
    """Render a Baileys QR string as a base64-encoded PNG (no data-URI prefix), or None when rendering fails."""
    try:
        import qrcode

        buffer = io.BytesIO()
        qrcode.make(qr_text, box_size=8, border=2).save(buffer, kind="PNG")
    except Exception:
        logger.warning("WhatsAppChannel: failed to render the pairing QR code as PNG", exc_info=True)
        return None
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class WhatsAppLoginMixin(BaseChannel):
    """QR-code login stream for ``WhatsAppChannel``.

    Requires the host class to provide the attributes below.
    """

    _qr_code: str | None

    def _login_event(
        self,
        status: LoginStatus,
        *,
        qr_png: str | None = None,
        error: str | None = None,
        progress: int = 0,
    ) -> LoginEvent:
        return LoginEvent(
            timestamp=time.time(),
            state=LoginState(
                status=status,
                method=LoginMethod.QR_CODE,
                qr_code_base64=qr_png,
                error_message=error,
                progress_percent=progress,
            ),
            channel_name=self.name,
        )

    # BaseChannel declares start_login as a coroutine; AsyncLoginProtocol implementations are async generators.
    async def start_login(  # type: ignore[override]
        self,
        method: object,
        *,
        timeout: float = 300.0,
        callback_url: str | None = None,
    ) -> AsyncGenerator[LoginEvent, None]:
        """Stream the QR pairing flow: every QR the bridge rotates in, then success, failure or timeout.

        The QR payload is a base64 PNG, the format ``AsyncLoginProtocol`` consumers render directly.
        """
        if method != LoginMethod.QR_CODE:
            raise ValueError("WhatsAppChannel only supports QR_CODE login method")

        queue: asyncio.Queue[LoginEvent] = asyncio.Queue()

        def on_qr(_name: str, data: object) -> None:
            qr_text = data.get("qr") if isinstance(data, dict) else None
            qr_png = _qr_png_base64(qr_text) if isinstance(qr_text, str) and qr_text else None
            if qr_png:
                queue.put_nowait(self._login_event(LoginStatus.WAITING_USER_ACTION, qr_png=qr_png, progress=30))

        def on_connection(_name: str, data: object) -> None:
            if not isinstance(data, dict):
                return
            if data.get("connected"):
                queue.put_nowait(self._login_event(LoginStatus.SUCCESS, progress=100))
            elif self._status == ChannelStatus.ERROR:
                queue.put_nowait(self._login_event(LoginStatus.FAILED, error="Connection failed or logged out"))

        # Subscribe before reading the current state so an event landing in between is not lost.
        self.on("qr_code", on_qr)
        self.on("connection_change", on_connection)
        try:
            if self.is_connected:
                yield self._login_event(LoginStatus.SUCCESS, progress=100)
                return

            current_png = _qr_png_base64(self._qr_code) if self._qr_code else None
            if current_png:
                yield self._login_event(LoginStatus.WAITING_USER_ACTION, qr_png=current_png, progress=30)
            else:
                yield self._login_event(LoginStatus.GENERATING, progress=10)

            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout
            # The deadline only wraps the queue wait: a timeout scope must not span a yield in an async generator.
            while (remaining := deadline - loop.time()) > 0:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=remaining)
                except TimeoutError:
                    break
                yield event
                if event.state.status in _TERMINAL_STATUSES:
                    return
            yield self._login_event(LoginStatus.TIMEOUT, error="Login timed out")
        finally:
            self.off("qr_code", on_qr)
            self.off("connection_change", on_connection)
