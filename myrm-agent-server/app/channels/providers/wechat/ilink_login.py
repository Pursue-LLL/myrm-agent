"""WeChat iLink QR code login (AsyncLoginProtocol).

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class; supplies the host members the mixin calls)
- channels.helpers::QRCodeLoginHelper (POS: QR code login state machine)
- channels.providers._ilink.client::ILinkClient (POS: iLink Bot protocol HTTP client)
- channels.protocols::LoginEvent, LoginMethod (POS: async login protocol types)

[OUTPUT]
- WeChatILinkLoginMixin: start_login / cancel_login and the QR fetch / poll callbacks used by WeChatILinkChannel

[POS]
Login half of WeChatILinkChannel. The host owns the client and channel lifecycle; the mixin only drives the QR scan
flow and swaps in the authenticated client when the scan succeeds.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import ChannelAuthError
from app.channels.helpers import QRCodeLoginHelper
from app.channels.protocols import LoginEvent, LoginMethod
from app.channels.providers._ilink.client import ILinkClient
from app.channels.providers._ilink.types import ILinkCredentials
from app.channels.types import ChannelStatus

logger = logging.getLogger(__name__)


class WeChatILinkLoginMixin(BaseChannel):
    """WeChat iLink QR code login for ``WeChatILinkChannel``.

    Requires the host class to provide the attributes below plus ``name``, ``_status`` and ``start`` from ``BaseChannel``.
    """

    _client: ILinkClient
    _login_helper: QRCodeLoginHelper | None

    # BaseChannel declares start_login as a coroutine; AsyncLoginProtocol implementations are async generators.
    async def start_login(  # type: ignore[override]
        self,
        method: object,
        *,
        timeout: float = 300.0,
        callback_url: str | None = None,
    ) -> AsyncIterator[LoginEvent]:
        """Start async QR code login flow.

        Implements AsyncLoginProtocol for WeChat iLink QR authentication.

        Args:
            method: LoginMethod.QR_CODE (only supported method)
            timeout: Maximum seconds to wait for QR scan
            callback_url: Not used (QR login does not require callback URL)

        Yields:
            LoginEvent: State change events

        Raises:
            ValueError: If method is not LoginMethod.QR_CODE
            ChannelAuthError: If QR fetch or polling fails
            TimeoutError: If login times out
        """
        if method != LoginMethod.QR_CODE:
            raise ValueError(f"Unsupported login method: {method}, expected QR_CODE")

        if self._client.http.is_closed:
            self._client = ILinkClient(self._client.credentials)

        self._login_helper = QRCodeLoginHelper(
            fetch_qr_fn=self._fetch_qr_code,
            poll_status_fn=self._poll_qr_status,
            max_refresh=3,
            qr_ttl=120.0,
            poll_interval=1.0,
        )

        async for event in self._login_helper.run(timeout, self.name):
            if event.credentials:
                creds = ILinkCredentials(
                    bot_token=event.credentials["bot_token"],
                    ilink_bot_id=event.credentials["ilink_bot_id"],
                    base_url=event.credentials.get("base_url", "https://ilinkai.weixin.qq.com"),
                    ilink_user_id=event.credentials.get("ilink_user_id"),
                )
                self._client = ILinkClient(creds)
                if self._status != ChannelStatus.RUNNING:
                    await self.start()
                logger.info("WeChatILinkChannel: QR login successful")

            yield event

    async def cancel_login(self) -> None:
        """Cancel current QR login flow."""
        if self._login_helper:
            self._login_helper.cancel()
        self._client._qr_code_cache = None
        logger.info("WeChatILinkChannel: QR login cancelled")

    async def _fetch_qr_code(self) -> tuple[str, bytes]:
        """Fetch QR code from iLink API.

        Returns:
            (qr_id, qr_image_bytes) where qr_id is the qrcode string
            and qr_image_bytes is the decoded PNG image.
        """
        import base64

        qr_id, qr_image_base64 = await self._client.fetch_qr_code()
        self._client._qr_code_cache = {"qr_id": qr_id, "qr_image_base64": qr_image_base64}
        qr_image_bytes = base64.b64decode(qr_image_base64)
        return qr_id, qr_image_bytes

    async def _poll_qr_status(self, qr_id: str) -> dict[str, str] | None:
        """Poll QR scan status.

        Args:
            qr_id: QR code ID from fetch

        Returns:
            Credentials dict if scanned, None if pending

        Raises:
            ChannelAuthError: If QR expired or polling failed
        """
        try:
            creds = await self._client.poll_qr_status(qr_id)
        except ChannelAuthError as exc:
            if "expired" in str(exc).lower():
                raise
            logger.error("WeChatILinkChannel: QR polling failed: %s", exc)
            raise

        if creds:
            return {
                "bot_token": creds.bot_token,
                "ilink_bot_id": creds.ilink_bot_id,
                "base_url": creds.base_url,
                "ilink_user_id": creds.ilink_user_id or "",
            }
        return None
