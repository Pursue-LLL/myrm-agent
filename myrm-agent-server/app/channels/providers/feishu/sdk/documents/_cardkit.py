"""Feishu CardKit streaming operations for FeishuClient.

[INPUT]
- ._host::FeishuHost (POS: members the host client supplies to the mixins)

[OUTPUT]
- FeishuCardKitMixin: streaming card create and update.

[POS]
CardKit streaming API methods of FeishuClient, used to stream a reply into an interactive card.
"""

from __future__ import annotations

import logging

from ._host import FeishuHost

logger = logging.getLogger(__name__)


class FeishuCardKitMixin(FeishuHost):
    """CardKit streaming card session."""

    async def streaming_card_create(
        self,
        card_id: str,
        *,
        seq: int = 1,
    ) -> bool:
        """Initialize a CardKit streaming card session."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.post(
            f"{self.api_base}/cardkit/v1/cards/{card_id}/streaming/contents",
            headers=self._auth(token),
            json={"content": "", "seq": seq},
        )
        body = self._safe_json(resp, "streaming_create")
        if body.get("code", -1) != 0:
            logger.debug("CardKit streaming create failed: %s", body.get("msg"))
            return False
        return True

    async def streaming_card_update(
        self,
        card_id: str,
        content: str,
        *,
        seq: int,
        is_final: bool = False,
    ) -> bool:
        """Append or finalize streaming content for a CardKit card."""
        token = await self.ensure_token()
        http = self._get_http()
        payload: dict[str, object] = {
            "content": content,
            "seq": seq,
        }
        if is_final:
            payload["is_final"] = True
        resp = await http.patch(
            f"{self.api_base}/cardkit/v1/cards/{card_id}/streaming/contents",
            headers=self._auth(token),
            json=payload,
        )
        body = self._safe_json(resp, "streaming_update")
        if body.get("code", -1) != 0:
            logger.debug("CardKit streaming update failed: %s", body.get("msg"))
            return False
        return True
