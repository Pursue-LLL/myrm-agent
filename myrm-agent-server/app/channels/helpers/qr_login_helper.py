"""QR code login helper for external channel authentication.

Provides reusable QR code login flow with auto-refresh and polling.

[INPUT]

[OUTPUT]
- QRCodeLoginHelper: Reusable QR login flow executor

[POS]
Helper layer for implementing AsyncLoginProtocol with QR code method.
Encapsulates auto-refresh, polling, timeout, and state streaming logic.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from app.channels.core.exceptions import (
    ChannelAuthError,
)
from app.channels.protocols.async_login import (
    LoginEvent,
    LoginMethod,
    LoginState,
    LoginStatus,
)

logger = logging.getLogger(__name__)

__all__ = ["QRCodeLoginHelper"]


class QRCodeLoginHelper:
    """QR code login flow helper with auto-refresh and polling.

    Encapsulates common QR login pattern:
    1. Fetch QR code from platform
    2. Display to user
    3. Poll for scan confirmation
    4. Auto-refresh QR on expiration
    5. Return credentials on success

    Example:
        helper = QRCodeLoginHelper(
            fetch_qr_fn=lambda: client.fetch_qr_code(),
            poll_status_fn=lambda qr_id: client.poll_qr_status(qr_id),
            max_refresh=3,
            qr_ttl=120.0,
            poll_interval=1.0,
        )

        async for event in helper.run(timeout=300.0, channel_name="wechat"):
            if event.state.status == LoginStatus.WAITING_USER_ACTION:
                display_qr_code(event.state.qr_code_base64)
            elif event.state.status == LoginStatus.SUCCESS:
                save_credentials(event.credentials)
                break
    """

    def __init__(
        self,
        fetch_qr_fn: Callable[[], Awaitable[tuple[str, bytes]]],
        poll_status_fn: Callable[[str], Awaitable[object | None]],
        max_refresh: int = 3,
        qr_ttl: float = 120.0,
        poll_interval: float = 1.0,
    ) -> None:
        """Initialize QR login helper.

        Args:
            fetch_qr_fn: Function to fetch QR code (returns qr_id, qr_image_bytes)
            poll_status_fn: Function to poll QR scan status (returns credentials or None)
            max_refresh: Maximum QR code refresh attempts on expiration
            qr_ttl: QR code lifetime in seconds before expiration
            poll_interval: Polling interval in seconds
        """
        self._fetch_qr_fn = fetch_qr_fn
        self._poll_status_fn = poll_status_fn
        self._max_refresh = max_refresh
        self._qr_ttl = qr_ttl
        self._poll_interval = poll_interval
        self._cancelled = False

    async def run(
        self,
        timeout: float,
        channel_name: str,
    ) -> AsyncIterator[LoginEvent]:
        """Execute QR login flow with auto-refresh and state streaming.

        Args:
            timeout: Maximum total seconds to wait for login
            channel_name: Channel name for event metadata

        Yields:
            LoginEvent: State change events (generating, waiting, success, etc.)

        Raises:
            TimeoutError: If login times out
            ChannelAuthError: If QR fetch or polling fails
        """
        self._cancelled = False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        yield self._create_event(
            LoginState(
                status=LoginStatus.GENERATING,
                method=LoginMethod.QR_CODE,
                progress_percent=10,
            ),
            channel_name,
        )

        for refresh_count in range(self._max_refresh + 1):
            if self._cancelled:
                yield self._create_event(
                    LoginState(
                        status=LoginStatus.CANCELLED,
                        method=LoginMethod.QR_CODE,
                    ),
                    channel_name,
                )
                return

            try:
                qr_id, qr_image_bytes = await self._fetch_qr_fn()
                qr_base64 = base64.b64encode(qr_image_bytes).decode("utf-8")
                qr_expires_at = loop.time() + self._qr_ttl

                logger.info(
                    "QR code generated (attempt %d/%d)",
                    refresh_count + 1,
                    self._max_refresh + 1,
                    extra={"channel": channel_name, "qr_id": qr_id},
                )

                yield self._create_event(
                    LoginState(
                        status=LoginStatus.WAITING_USER_ACTION,
                        method=LoginMethod.QR_CODE,
                        qr_code_base64=qr_base64,
                        qr_expires_at=qr_expires_at,
                        progress_percent=30,
                    ),
                    channel_name,
                )

            except Exception as exc:
                logger.error(
                    "QR code fetch failed",
                    extra={"channel": channel_name, "error": str(exc)},
                    exc_info=True,
                )
                yield self._create_event(
                    LoginState(
                        status=LoginStatus.FAILED,
                        method=LoginMethod.QR_CODE,
                        error_message=f"Failed to fetch QR code: {exc}",
                    ),
                    channel_name,
                )
                raise ChannelAuthError(
                    f"QR code fetch failed: {exc}",
                    channel=channel_name,
                ) from exc

            while loop.time() < deadline and loop.time() < qr_expires_at:
                if self._cancelled:
                    yield self._create_event(
                        LoginState(
                            status=LoginStatus.CANCELLED,
                            method=LoginMethod.QR_CODE,
                        ),
                        channel_name,
                    )
                    return

                try:
                    credentials = await self._poll_status_fn(qr_id)
                except ChannelAuthError as exc:
                    if "expired" in str(exc).lower():
                        logger.info(
                            "QR code expired, refreshing",
                            extra={"channel": channel_name},
                        )
                        break

                    logger.error(
                        "QR polling failed",
                        extra={"channel": channel_name, "error": str(exc)},
                        exc_info=True,
                    )
                    yield self._create_event(
                        LoginState(
                            status=LoginStatus.FAILED,
                            method=LoginMethod.QR_CODE,
                            error_message=str(exc),
                        ),
                        channel_name,
                    )
                    raise

                if credentials:
                    logger.info(
                        "QR login successful",
                        extra={"channel": channel_name},
                    )
                    yield self._create_event(
                        LoginState(
                            status=LoginStatus.SUCCESS,
                            method=LoginMethod.QR_CODE,
                            progress_percent=100,
                        ),
                        channel_name,
                        credentials,
                    )
                    return

                await asyncio.sleep(self._poll_interval)

            if self._cancelled:
                yield self._create_event(
                    LoginState(
                        status=LoginStatus.CANCELLED,
                        method=LoginMethod.QR_CODE,
                    ),
                    channel_name,
                )
                return

        if self._cancelled:
            yield self._create_event(
                LoginState(
                    status=LoginStatus.CANCELLED,
                    method=LoginMethod.QR_CODE,
                ),
                channel_name,
            )
            return

        logger.warning(
            "QR login timeout",
            extra={"channel": channel_name},
        )
        yield self._create_event(
            LoginState(
                status=LoginStatus.TIMEOUT,
                method=LoginMethod.QR_CODE,
                error_message="Login timeout: QR code expired",
            ),
            channel_name,
        )
        raise TimeoutError(f"{channel_name} QR login timeout")

    def cancel(self) -> None:
        """Cancel current login flow.

        Sets internal flag to stop polling on next iteration.
        """
        self._cancelled = True
        logger.info("QR login cancelled")

    def _create_event(
        self,
        state: LoginState,
        channel_name: str,
        credentials: dict[str, str] | None = None,
    ) -> LoginEvent:
        """Create login event with current timestamp."""
        return LoginEvent(
            timestamp=time.time(),
            state=state,
            channel_name=channel_name,
            credentials=credentials,
        )
