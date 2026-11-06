"""[INPUT]
- .common (POS: shared primitives)

[OUTPUT]
- ClipConfigMixin

[POS]
Extension bridge mixin: clip-agent config push to the extension.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


from .common import (
    logger,
)


class ClipConfigMixin:
    async def notify_clip_agent_config(
        self,
        agent_id: str | None,
        web_ui_origin: str | None,
    ) -> None:
        """Push wiki clip agent scope to the connected extension."""
        if not self._connected or not self._ws:
            return
        try:
            await self._ws.send_text(
                json.dumps(
                    {
                        "type": "clip_agent_update",
                        "agent_id": agent_id,
                        "web_ui_origin": web_ui_origin,
                    }
                )
            )
        except Exception as exc:
            logger.warning("Failed to notify extension of clip agent change: %s", exc)
