"""iLink Bot protocol HTTP client for WeChat personal account integration.

Implements the core iLink HTTP API:
- QR code login flow
- Long-polling message retrieval (getupdates)
- Message sending (sendmessage)
- Media upload URL acquisition
- Typing indicator support
- Bot config retrieval

[INPUT]
- httpx::AsyncClient (HTTP client, single instance reused)

[OUTPUT]
- ILinkClient: iLink Bot API client
- login_with_qr: QR code login flow

[POS]
iLink Bot protocol HTTP client. Single-instance httpx connection reuse with unified exception mapping.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import secrets

import httpx

from app.channels.core.exceptions import (
    ChannelAuthError,
    ChannelConnectionError,
)
from app.channels.providers._ilink.types import (
    DEFAULT_BASE_URL,
    CDNMediaType,
    ILinkCredentials,
    ILinkMessage,
    MessageItem,
    MessageState,
    MessageType,
    TypingStatus,
    parse_item,
    serialize_item,
)

logger = logging.getLogger(__name__)
_LONG_POLL_TIMEOUT = 35.0
_SEND_TIMEOUT = 15.0
_QR_POLL_TIMEOUT = 35.0
_SESSION_EXPIRED_ERRCODE = -14
_ILINK_APP_ID = "bot"
_ILINK_APP_VERSION = "2.1.1"
_ILINK_APP_CLIENT_VERSION = str((2 << 16) | (1 << 8) | 1)


class ILinkClient:
    """iLink Bot HTTP API client with connection reuse and unified error handling."""

    def __init__(
        self,
        credentials: ILinkCredentials | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._creds = credentials
        self._base_url = credentials.base_url if credentials else DEFAULT_BASE_URL
        self._wechat_uin = self._generate_wechat_uin()
        self._qr_code_cache: str | None = None
        self._http = http_client or httpx.AsyncClient()
        self._owns_http = http_client is None

    @property
    def credentials(self) -> ILinkCredentials | None:
        return self._creds

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def http(self) -> httpx.AsyncClient:
        return self._http

    @property
    def qr_code_cache(self) -> str | None:
        return self._qr_code_cache

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    @staticmethod
    def _generate_wechat_uin() -> str:
        uint32 = secrets.randbits(32)
        return base64.b64encode(str(uint32).encode()).decode()

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-WECHAT-UIN": self._wechat_uin,
            "iLink-App-Id": _ILINK_APP_ID,
            "iLink-App-ClientVersion": _ILINK_APP_CLIENT_VERSION,
        }
        if self._creds:
            headers["AuthorizationType"] = "ilink_bot_token"
            headers["Authorization"] = f"Bearer {self._creds.bot_token}"
        return headers

    async def _post(
        self,
        endpoint: str,
        body: dict[str, object],
        timeout: float = _SEND_TIMEOUT,
    ) -> dict[str, object]:
        url = f"{self._base_url}/{endpoint}"
        try:
            resp = await self._http.post(url, json=body, headers=self._build_headers(), timeout=timeout)
        except httpx.ConnectError as exc:
            raise ChannelConnectionError(f"iLink connection failed: {exc}", channel="wechat") from exc
        except httpx.TimeoutException as exc:
            raise ChannelConnectionError(f"iLink request timeout: {exc}", channel="wechat") from exc

        if resp.status_code != 200:
            raise ChannelConnectionError(f"iLink API error: HTTP {resp.status_code}", channel="wechat")

        data = resp.json()
        if not isinstance(data, dict):
            raise ChannelConnectionError(f"iLink API returned non-dict: {type(data)}", channel="wechat")

        self._check_session_expired(data)
        return data

    @staticmethod
    def _check_session_expired(data: dict[str, object]) -> None:
        if data.get("errcode") == _SESSION_EXPIRED_ERRCODE or data.get("ret") == _SESSION_EXPIRED_ERRCODE:
            raise ChannelAuthError(
                f"WeChat session expired (errcode={data.get('errcode')} ret={data.get('ret')})",
                channel="wechat",
            )

    # ── QR Login ───────────────────────────────────────────────────────

    async def fetch_qr_code(self) -> tuple[str, str]:
        """Fetch QR code for login. Returns (qrcode, qrcode_img_content)."""
        url = f"{DEFAULT_BASE_URL}/ilink/bot/get_bot_qrcode?bot_type=3"
        try:
            resp = await self._http.get(url, timeout=10.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ChannelConnectionError(f"Failed to fetch QR code: {exc}", channel="wechat") from exc

        data = resp.json()
        qrcode = data.get("qrcode", "")
        img_content = data.get("qrcode_img_content", "")
        if not isinstance(qrcode, str) or not isinstance(img_content, str):
            raise ChannelConnectionError("Invalid QR code response", channel="wechat")
        return qrcode, img_content

    async def poll_qr_status(self, qrcode: str) -> ILinkCredentials | None:
        """Poll QR code status. Returns credentials if confirmed, None if waiting."""
        url = f"{DEFAULT_BASE_URL}/ilink/bot/get_qrcode_status?qrcode={qrcode}"
        try:
            resp = await self._http.get(url, timeout=_QR_POLL_TIMEOUT + 5)
            resp.raise_for_status()
        except httpx.TimeoutException:
            return None
        except httpx.HTTPError as exc:
            raise ChannelConnectionError(f"QR poll failed: {exc}", channel="wechat") from exc

        data = resp.json()
        status = data.get("status", "")

        if status == "confirmed":
            bot_token = data.get("bot_token")
            ilink_bot_id = data.get("ilink_bot_id")
            if not isinstance(bot_token, str) or not isinstance(ilink_bot_id, str):
                raise ChannelAuthError(
                    "Missing bot_token or ilink_bot_id in confirmed response",
                    channel="wechat",
                )
            return ILinkCredentials(
                bot_token=bot_token,
                ilink_bot_id=ilink_bot_id,
                base_url=data.get("baseurl", DEFAULT_BASE_URL),
                ilink_user_id=(data["ilink_user_id"] if isinstance(data.get("ilink_user_id"), str) else None),
            )

        if status == "expired":
            raise ChannelAuthError("QR code expired", channel="wechat")

        return None

    # ── Long-polling ───────────────────────────────────────────────────

    async def get_updates(self, get_updates_buf: str = "") -> tuple[list[ILinkMessage], str]:
        """Long-poll for new messages. Returns (messages, new_buf)."""
        if not self._creds:
            raise ChannelAuthError("ILinkClient not authenticated", channel="wechat")

        body: dict[str, object] = {
            "get_updates_buf": get_updates_buf,
            "base_info": {"channel_version": _ILINK_APP_VERSION},
        }

        try:
            data = await self._post("ilink/bot/getupdates", body, timeout=_LONG_POLL_TIMEOUT + 5)
        except ChannelConnectionError:
            return [], get_updates_buf

        ret = data.get("ret")
        if ret is not None and ret != 0:
            errcode = data.get("errcode", 0)
            errmsg = data.get("errmsg", "")
            if ret == -1 and errcode == 0:
                logger.debug("iLink getUpdates: long-poll empty (ret=-1), normal cycle")
                new_buf = data.get("get_updates_buf", get_updates_buf)
                return [], new_buf if isinstance(new_buf, str) else get_updates_buf
            raise ChannelConnectionError(
                f"iLink getUpdates failed: ret={ret} errcode={errcode} errmsg={errmsg}",
                channel="wechat",
            )

        msgs_raw = data.get("msgs", [])
        new_buf = data.get("get_updates_buf", get_updates_buf)

        messages: list[ILinkMessage] = []
        for msg_data in msgs_raw if isinstance(msgs_raw, list) else []:
            if not isinstance(msg_data, dict):
                continue
            msg = self._parse_message(msg_data)
            if msg:
                messages.append(msg)

        return messages, new_buf if isinstance(new_buf, str) else get_updates_buf

    @staticmethod
    def _parse_message(msg_data: dict[str, object]) -> ILinkMessage | None:
        items_raw = msg_data.get("item_list", [])
        items: list[MessageItem] = []

        for item_data in items_raw if isinstance(items_raw, list) else []:
            if not isinstance(item_data, dict):
                continue
            item = parse_item(item_data)
            if item:
                items.append(item)

        from_user = msg_data.get("from_user_id")
        to_user = msg_data.get("to_user_id")
        if not isinstance(from_user, str) or not isinstance(to_user, str):
            return None

        raw_name = msg_data.get("from_user_name")
        from_user_name = str(raw_name) if isinstance(raw_name, str) and raw_name else None

        return ILinkMessage(
            from_user_id=from_user,
            to_user_id=to_user,
            message_type=int(msg_data.get("message_type", 0)),
            message_state=int(msg_data.get("message_state", 0)),
            item_list=tuple(items),
            context_token=msg_data.get("context_token") if isinstance(msg_data.get("context_token"), str) else None,
            message_id=int(msg_data["message_id"]) if isinstance(msg_data.get("message_id"), int) else None,
            session_id=msg_data.get("session_id") if isinstance(msg_data.get("session_id"), str) else None,
            group_id=msg_data.get("group_id") if isinstance(msg_data.get("group_id"), str) else None,
            from_user_name=from_user_name,
        )

    # ── Send ───────────────────────────────────────────────────────────

    async def send_message(
        self,
        to_user_id: str,
        items: list[MessageItem],
        context_token: str | None = None,
    ) -> None:
        if not self._creds:
            raise ChannelAuthError("ILinkClient not authenticated", channel="wechat")

        msg: dict[str, object] = {
            "from_user_id": self._creds.ilink_bot_id,
            "to_user_id": to_user_id,
            "client_id": secrets.token_hex(16),
            "message_type": MessageType.BOT,
            "message_state": MessageState.FINISH,
            "item_list": [serialize_item(item) for item in items],
        }
        if context_token:
            msg["context_token"] = context_token

        body: dict[str, object] = {
            "msg": msg,
            "base_info": {"channel_version": _ILINK_APP_VERSION},
        }

        data = await self._post("ilink/bot/sendmessage", body)
        ret = data.get("ret")
        if ret is not None and ret != 0:
            raise ChannelConnectionError(
                f"iLink sendMessage failed: ret={ret} errmsg={data.get('errmsg', '')}",
                channel="wechat",
            )

    # ── Config & Typing ────────────────────────────────────────────────

    async def get_config(self, ilink_user_id: str, context_token: str | None = None) -> dict[str, object]:
        if not self._creds:
            raise ChannelAuthError("ILinkClient not authenticated", channel="wechat")

        body: dict[str, object] = {
            "ilink_user_id": ilink_user_id,
            "base_info": {"channel_version": _ILINK_APP_VERSION},
        }
        if context_token:
            body["context_token"] = context_token

        data = await self._post("ilink/bot/getconfig", body, timeout=10.0)
        ret = data.get("ret")
        if ret is not None and ret != 0:
            raise ChannelConnectionError(
                f"iLink getConfig failed: ret={ret} errmsg={data.get('errmsg', '')}",
                channel="wechat",
            )
        return data

    async def send_typing(self, ilink_user_id: str, typing_ticket: str, status: TypingStatus) -> None:
        if not self._creds:
            raise ChannelAuthError("ILinkClient not authenticated", channel="wechat")

        body: dict[str, object] = {
            "ilink_user_id": ilink_user_id,
            "typing_ticket": typing_ticket,
            "status": status,
            "base_info": {"channel_version": _ILINK_APP_VERSION},
        }
        data = await self._post("ilink/bot/sendtyping", body, timeout=10.0)
        ret = data.get("ret")
        if ret is not None and ret != 0:
            logger.warning("iLink sendTyping failed: ret=%s errmsg=%s", ret, data.get("errmsg", ""))

    # ── Media Upload ───────────────────────────────────────────────────

    async def get_upload_url(
        self,
        to_user_id: str,
        media_type: CDNMediaType,
        file_size: int,
        raw_file_md5: str,
        aes_key: str,
    ) -> str:
        """Get pre-signed CDN upload URL for media."""
        if not self._creds:
            raise ChannelAuthError("ILinkClient not authenticated", channel="wechat")

        body: dict[str, object] = {
            "filekey": secrets.token_hex(16),
            "media_type": media_type,
            "to_user_id": to_user_id,
            "rawsize": file_size,
            "rawfilemd5": raw_file_md5,
            "filesize": file_size,
            "no_need_thumb": True,
            "aeskey": aes_key,
            "base_info": {"channel_version": _ILINK_APP_VERSION},
        }

        data = await self._post("ilink/bot/getuploadurl", body)
        ret = data.get("ret")
        if ret is not None and ret != 0:
            raise ChannelConnectionError(
                f"iLink getUploadURL failed: ret={ret} errmsg={data.get('errmsg', '')}",
                channel="wechat",
            )

        upload_param = data.get("upload_param", "")
        if not isinstance(upload_param, str):
            raise ChannelConnectionError("Invalid upload_param in response", channel="wechat")
        return upload_param


# ── QR Login Flow ──────────────────────────────────────────────────────


_MAX_QR_REFRESH = 3


async def login_with_qr(
    timeout: float = 480.0,
    client: ILinkClient | None = None,
) -> ILinkCredentials:
    """Perform QR code login flow with auto-refresh on expiration.

    Automatically refreshes the QR code up to ``_MAX_QR_REFRESH`` times
    when it expires before the user scans it.
    """
    c = client or ILinkClient()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    for refresh_count in range(_MAX_QR_REFRESH + 1):
        qrcode, img_content = await c.fetch_qr_code()
        c._qr_code_cache = img_content
        logger.info(
            "WeChat login: scan QR code (attempt %d/%d)",
            refresh_count + 1,
            _MAX_QR_REFRESH + 1,
        )

        try:
            import qrcode as qrcode_lib

            qr = qrcode_lib.QRCode()
            qr.add_data(img_content)
            qr.print_ascii()
        except (ImportError, TypeError):
            pass

        while loop.time() < deadline:
            try:
                creds = await c.poll_qr_status(qrcode)
            except ChannelAuthError as exc:
                if "expired" in str(exc).lower():
                    logger.info("WeChat login: QR code expired, refreshing")
                    break
                raise
            if creds:
                c._qr_code_cache = None
                logger.info("WeChat login successful: bot_id=%s", creds.ilink_bot_id)
                return creds
            await asyncio.sleep(1.0)
        else:
            break

    c._qr_code_cache = None
    raise ChannelAuthError("WeChat login timeout", channel="wechat")
