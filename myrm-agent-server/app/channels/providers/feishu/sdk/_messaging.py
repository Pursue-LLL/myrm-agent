"""Feishu messaging and media Mixin for FeishuClient.

[INPUT]
- .exceptions::FeishuRateLimitError, FeishuSendError (POS: Feishu-specific API error hierarchy.)

[OUTPUT]
- FeishuMessagingMixin: Mixin providing messaging and media upload/download operations.

[POS]
Mixin that adds IM messaging, reactions, and media methods to FeishuClient.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.channels.providers.feishu.sdk.exceptions import (
    FeishuRateLimitError,
    FeishuSendError,
)

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)


class FeishuMessagingMixin:
    """Messaging and media operations for FeishuClient.

    Requires the host class to provide:
    - ``ensure_token() -> str``
    - ``_get_http() -> httpx.AsyncClient``
    - ``_auth(token) -> dict``
    - ``_safe_json(resp, op) -> dict``
    - ``api_base: str``
    """

    api_base: str
    _MEDIA_TIMEOUT: float

    async def ensure_token(self) -> str: ...
    def _get_http(self) -> httpx.AsyncClient: ...
    def _auth(self, token: str) -> dict[str, str]: ...
    def _safe_json(self, resp: httpx.Response, operation: str) -> dict[str, object]: ...

    # ── Messages ─────────────────────────────────────────────────

    async def send_message(
        self,
        receive_id: str,
        msg_type: str,
        content: str,
        *,
        receive_id_type: str = "chat_id",
        reply_in_thread: bool = False,
    ) -> str | None:
        """Send a message and return the message_id."""
        token = await self.ensure_token()
        payload: dict[str, object] = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": content,
        }
        if reply_in_thread:
            payload["reply_in_thread"] = True

        http = self._get_http()
        resp = await http.post(
            f"{self.api_base}/im/v1/messages?receive_id_type={receive_id_type}",
            headers=self._auth(token),
            json=payload,
        )

        if resp.status_code == 429:
            raise FeishuRateLimitError("Feishu send rate limited")
        if resp.status_code >= 400:
            body = self._safe_json(resp, "send")
            detail = str(body.get("msg", resp.status_code))
            raise FeishuSendError(
                f"Feishu send failed: {detail}",
                status_code=resp.status_code,
                retriable=resp.status_code >= 500,
            )

        body = self._safe_json(resp, "send")
        if body.get("code", -1) != 0:
            logger.warning("Feishu send failed: %s", body.get("msg"))
            return None

        data = body.get("data", {})
        message_id = data.get("message_id") if isinstance(data, dict) else None
        return str(message_id) if message_id else None

    async def reply_message(
        self,
        message_id: str,
        msg_type: str,
        content: str,
        *,
        reply_in_thread: bool = False,
    ) -> str | None:
        """Reply to a specific message and return the new message_id."""
        token = await self.ensure_token()
        payload: dict[str, object] = {
            "msg_type": msg_type,
            "content": content,
        }
        if reply_in_thread:
            payload["reply_in_thread"] = True

        http = self._get_http()
        resp = await http.post(
            f"{self.api_base}/im/v1/messages/{message_id}/reply",
            headers=self._auth(token),
            json=payload,
        )

        if resp.status_code == 429:
            raise FeishuRateLimitError("Feishu reply rate limited")
        if resp.status_code >= 400:
            body_data = self._safe_json(resp, "reply")
            detail = str(body_data.get("msg", resp.status_code))
            raise FeishuSendError(
                f"Feishu reply failed: {detail}",
                status_code=resp.status_code,
                retriable=resp.status_code >= 500,
            )

        body_data = self._safe_json(resp, "reply")
        if body_data.get("code", -1) != 0:
            logger.warning("Feishu reply failed: %s", body_data.get("msg"))
            return None

        data = body_data.get("data", {})
        new_message_id = data.get("message_id") if isinstance(data, dict) else None
        return str(new_message_id) if new_message_id else None

    async def update_message(self, message_id: str, msg_type: str, content: str) -> bool:
        """Update an existing message (alias for patch_message)."""
        return await self.patch_message(message_id, msg_type, content)

    async def edit_message(self, message_id: str, msg_type: str, content: str) -> bool:
        """Edit a previously sent message.

        API: PUT /im/v1/messages/{message_id}
        """
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.put(
            f"{self.api_base}/im/v1/messages/{message_id}",
            headers=self._auth(token),
            json={"msg_type": msg_type, "content": content},
        )

        body = self._safe_json(resp, "edit")
        if body.get("code", -1) != 0:
            logger.warning("Feishu edit failed: %s", body.get("msg"))
            return False
        return True

    async def patch_message(self, message_id: str, msg_type: str, content: str) -> bool:
        """Update a message via PATCH (for interactive card updates)."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.patch(
            f"{self.api_base}/im/v1/messages/{message_id}",
            headers=self._auth(token),
            json={"msg_type": msg_type, "content": content},
        )
        if resp.status_code >= 400:
            logger.debug("Feishu patch failed: HTTP %d", resp.status_code)
            return False
        return True

    async def delete_message(self, message_id: str) -> bool:
        """Delete a previously sent message."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.delete(
            f"{self.api_base}/im/v1/messages/{message_id}",
            headers=self._auth(token),
        )

        body = self._safe_json(resp, "delete")
        if body.get("code", -1) != 0:
            logger.warning("Feishu delete failed: %s", body.get("msg"))
            return False
        return True

    async def add_reaction(self, message_id: str, emoji_type: str = "OK") -> str | None:
        """Add an emoji reaction to a message."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.post(
            f"{self.api_base}/im/v1/messages/{message_id}/reactions",
            headers=self._auth(token),
            json={"reaction_type": {"emoji_type": emoji_type}},
        )
        body = self._safe_json(resp, "add_reaction")
        if body.get("code", -1) != 0:
            logger.debug("Feishu add_reaction failed: %s", body.get("msg"))
            return None
        data = body.get("data", {})
        if isinstance(data, dict):
            rid = data.get("reaction_id")
            return str(rid) if rid else None
        return None

    async def delete_reaction(self, message_id: str, reaction_id: str) -> bool:
        """Remove an emoji reaction from a message."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.delete(
            f"{self.api_base}/im/v1/messages/{message_id}/reactions/{reaction_id}",
            headers=self._auth(token),
        )
        body = self._safe_json(resp, "delete_reaction")
        if body.get("code", -1) != 0:
            logger.debug("Feishu delete_reaction failed: %s", body.get("msg"))
            return False
        return True

    async def get_message(self, message_id: str) -> dict[str, object] | None:
        """Fetch a message by ID and return its body content."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.get(
            f"{self.api_base}/im/v1/messages/{message_id}",
            headers=self._auth(token),
        )
        body = self._safe_json(resp, "get_message")
        if body.get("code", -1) != 0:
            return None
        data = body.get("data", {})
        if not isinstance(data, dict):
            return None
        items = data.get("items")
        if not isinstance(items, list) or not items:
            return None
        msg_obj = items[0]
        if not isinstance(msg_obj, dict):
            return None
        return msg_obj

    # ── Media ────────────────────────────────────────────────────

    async def upload_image(self, image_data: bytes) -> str | None:
        """Upload an image and return its image_key."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.post(
            f"{self.api_base}/im/v1/images",
            headers=self._auth(token),
            files={"image": ("image.png", image_data, "image/png")},
            data={"image_type": "message"},
            timeout=self._MEDIA_TIMEOUT,
        )

        body = self._safe_json(resp, "upload_image")
        if body.get("code", -1) != 0:
            logger.warning("Feishu image upload failed: %s", body.get("msg"))
            return None

        data = body.get("data", {})
        image_key = data.get("image_key") if isinstance(data, dict) else None
        return str(image_key) if image_key else None

    async def download_image(self, image_key: str) -> bytes | None:
        """Download an image by its image_key."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.get(
            f"{self.api_base}/im/v1/images/{image_key}",
            headers=self._auth(token),
            timeout=self._MEDIA_TIMEOUT,
        )

        if resp.status_code != 200:
            logger.warning("Feishu image download failed: HTTP %d", resp.status_code)
            return None
        return resp.content

    async def download_message_resource(
        self,
        message_id: str,
        file_key: str,
        resource_type: str = "image",
    ) -> bytes | None:
        """Download a resource (image/file/audio) from a specific message."""
        token = await self.ensure_token()
        url = f"{self.api_base}/im/v1/messages/{message_id}/resources/{file_key}?type={resource_type}"
        http = self._get_http()
        resp = await http.get(
            url,
            headers=self._auth(token),
            timeout=self._MEDIA_TIMEOUT,
        )

        if resp.status_code != 200:
            logger.warning("Feishu resource download failed: HTTP %d", resp.status_code)
            return None
        return resp.content

    async def upload_file(
        self,
        file_data: bytes,
        file_name: str,
        file_type: str = "stream",
    ) -> str | None:
        """Upload a file and return its file_key."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.post(
            f"{self.api_base}/im/v1/files",
            headers=self._auth(token),
            files={"file": (file_name, file_data, "application/octet-stream")},
            data={"file_type": file_type, "file_name": file_name},
            timeout=self._MEDIA_TIMEOUT,
        )

        body = self._safe_json(resp, "upload_file")
        if body.get("code", -1) != 0:
            logger.warning("Feishu file upload failed: %s", body.get("msg"))
            return None

        data = body.get("data", {})
        file_key = data.get("file_key") if isinstance(data, dict) else None
        return str(file_key) if file_key else None

    async def get_freebusy(
        self,
        user_ids: list[str],
        start: str,
        end: str,
        *,
        user_access_token: str | None = None,
        user_id_type: str = "open_id",
    ) -> list[dict[str, object]]:
        """Fetch free/busy status for a list of users.

        Security: Supports ``user_access_token`` for strict privilege isolation.
        """
        token = user_access_token if user_access_token else await self.ensure_token()
        http = self._get_http()

        all_results = []
        for uid in user_ids:
            resp = await http.post(
                f"{self.api_base}/calendar/v4/freebusy/list?user_id_type={user_id_type}",
                headers=self._auth(token),
                json={
                    "time_min": start,
                    "time_max": end,
                    "user_id": uid,
                },
            )
            body = self._safe_json(resp, "get_freebusy")
            if body.get("code", -1) != 0:
                logger.warning("Feishu get_freebusy failed for %s: %s", uid, body.get("msg"))
                continue

            data = body.get("data", {})
            fb_list = data.get("freebusy_list", [])
            busy_slots = []
            if isinstance(fb_list, list):
                for fb in fb_list:
                    bs = fb.get("start_time")
                    be = fb.get("end_time")
                    if bs and be:
                        busy_slots.append({"start": bs, "end": be})

            all_results.append({"user_id": uid, "busy_slots": busy_slots})

        return all_results
