"""Feishu OpenAPI client — token management, HTTP core, and Mixin composition.

Async client for Feishu/Lark OpenAPI. Handles tenant_access_token lifecycle
(auto-refresh with configurable TTL buffer) and provides connection pooling
via a shared httpx.AsyncClient.

API methods are split across Mixins by domain:
- ``_messaging.py``: IM messages, reactions, media upload/download, calendar
- ``_documents.py``: Drive meta, comments, wiki, CardKit streaming, Bitable, Docx

[INPUT]
- .exceptions::FeishuAuthError (POS: Feishu-specific API error hierarchy.)
- ._messaging::FeishuMessagingMixin (POS: IM messaging, media, and group operations.)
- ._documents::FeishuDocumentsMixin (POS: Drive, comment, wiki, CardKit, Bitable, Docx operations.)
- myrm_agent_harness.utils.coercion::parse_float (POS: Safe numeric parsing with bounds clamping.)

[OUTPUT]
- FeishuClient: async API client for Feishu OpenAPI

[POS]
Standalone Feishu OpenAPI client.
Usable by any module that needs Feishu API access (channels, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
from myrm_agent_harness.utils.coercion import parse_float

from app.channels.providers.feishu.sdk._documents import FeishuDocumentsMixin
from app.channels.providers.feishu.sdk._messaging import FeishuMessagingMixin
from app.channels.providers.feishu.sdk.exceptions import FeishuAuthError

logger = logging.getLogger(__name__)

_FEISHU_API = "https://open.feishu.cn/open-apis"
_LARK_API = "https://open.larksuite.com/open-apis"

_MIN_TIMEOUT: float = 1.0
_MAX_TIMEOUT: float = 300.0


def _resolve_timeout(default: float, override: float | None = None) -> float:
    """Resolve HTTP timeout with safety clamp to [1.0, 300.0]."""
    value = override if override is not None else default
    return parse_float(value, _MIN_TIMEOUT, min_val=_MIN_TIMEOUT, max_val=_MAX_TIMEOUT)


_TIMEOUT = _resolve_timeout(15.0)
_MEDIA_TIMEOUT = _resolve_timeout(30.0)
_TOKEN_REFRESH_BUFFER = 300


class FeishuClient(FeishuMessagingMixin, FeishuDocumentsMixin):
    """Async client for Feishu OpenAPI with auto-refreshing token.

    Uses a shared httpx.AsyncClient for connection pooling.
    Call ``close()`` during application shutdown to release resources.

    API methods are organized by domain via Mixins:
    - Messaging / Media: see ``_messaging.py``
    - Documents / Comments / Wiki / CardKit / Bitable: see ``_documents.py``
    """

    _MEDIA_TIMEOUT: float = _MEDIA_TIMEOUT

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        use_lark: bool = False,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self.api_base = _LARK_API if use_lark else _FEISHU_API
        self._token: str = ""
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None
        self.bot_open_id: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self._app_id and self._app_secret)

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=_TIMEOUT)
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    async def ensure_token(self) -> str:
        """Return a valid tenant_access_token, refreshing if expired."""
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token

        async with self._token_lock:
            if self._token and time.monotonic() < self._token_expires_at:
                return self._token

            http = self._get_http()
            resp = await http.post(
                f"{self.api_base}/auth/v3/tenant_access_token/internal",
                json={"app_id": self._app_id, "app_secret": self._app_secret},
            )
            if resp.status_code != 200:
                raise FeishuAuthError(
                    f"Feishu token refresh failed: HTTP {resp.status_code}",
                )
            data = resp.json()
            code = data.get("code", -1)
            if code != 0:
                raise FeishuAuthError(
                    f"Feishu token error: code={code}, msg={data.get('msg')}",
                )

            self._token = data["tenant_access_token"]
            expire = int(data.get("expire", 7200))
            self._token_expires_at = time.monotonic() + expire - _TOKEN_REFRESH_BUFFER
            logger.info("Feishu token refreshed, expires in %ds", expire)
            return self._token

    async def fetch_bot_info(self) -> str:
        """Fetch bot info and return bot open_id."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.get(
            f"{self.api_base}/bot/v3/info",
            headers=self._auth(token),
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json().get("bot", {})
            self.bot_open_id = str(data.get("open_id", ""))
        return self.bot_open_id

    async def verify_connectivity(self) -> bool:
        """Verify API connectivity by refreshing the token."""
        try:
            await self.ensure_token()
            return True
        except Exception:
            return False

    async def download_url(self, url: str, *, timeout: float = 30.0) -> bytes | None:
        """Download arbitrary URL content."""
        http = self._get_http()
        try:
            resp = await http.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.content
        except Exception:
            logger.warning("Failed to download URL: %s", url)
            return None

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _safe_json(self, resp: httpx.Response, operation: str) -> dict[str, object]:
        """Safely parse a Feishu API JSON response."""
        if not resp.is_success:
            return {"code": resp.status_code, "msg": f"HTTP {resp.status_code}"}
        try:
            body = resp.json()
            if not isinstance(body, dict):
                logger.warning(
                    "Feishu %s: unexpected response type %s",
                    operation,
                    type(body).__name__,
                )
                return {"code": -1, "msg": "Unexpected response format"}
            return body
        except Exception:
            logger.warning("Feishu %s: non-JSON response body", operation)
            return {"code": -1, "msg": "Non-JSON response"}
