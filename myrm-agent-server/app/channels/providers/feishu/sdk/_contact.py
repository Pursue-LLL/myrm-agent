"""Feishu contact Mixin for FeishuClient — user info resolution.

[INPUT]
- (none — uses host class methods only)

[OUTPUT]
- FeishuContactMixin: Mixin providing contact/user lookup operations.

[POS]
Mixin that adds contact-domain API methods to FeishuClient: user info lookup
by open_id. Used by FeishuUserResolver to resolve sender display names.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)


class FeishuContactMixin:
    """Contact-domain operations for FeishuClient.

    Requires the host class to provide:
    - ``ensure_token() -> str``
    - ``_get_http() -> httpx.AsyncClient``
    - ``_auth(token) -> dict``
    - ``_safe_json(resp, op) -> dict``
    - ``api_base: str``
    """

    api_base: str

    async def ensure_token(self) -> str: ...
    def _get_http(self) -> httpx.AsyncClient: ...
    def _auth(self, token: str) -> dict[str, str]: ...
    def _safe_json(self, resp: httpx.Response, operation: str) -> dict[str, object]: ...

    async def get_user(self, open_id: str) -> dict[str, object] | None:
        """Fetch a user's contact info by open_id.

        Returns the ``data.user`` object (with ``name``) or None on failure.
        """
        if not open_id:
            return None
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.get(
            f"{self.api_base}/contact/v3/users/{open_id}",
            params={"user_id_type": "open_id"},
            headers=self._auth(token),
        )
        body = self._safe_json(resp, "get_user")
        if body.get("code", -1) != 0:
            logger.debug("Feishu get_user failed: %s", body.get("msg"))
            return None
        data = body.get("data", {})
        if not isinstance(data, dict):
            return None
        user = data.get("user")
        if not isinstance(user, dict):
            return None
        return user
