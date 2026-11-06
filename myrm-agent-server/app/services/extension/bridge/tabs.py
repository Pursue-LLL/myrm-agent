"""[INPUT]
- .common (POS: shared primitives)

[OUTPUT]
- TabsMixin

[POS]
Extension bridge mixin: tab listing and tab-move requests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


from .common import (
    ExtensionTab,
    logger,
)


class TabsMixin:
    async def list_tabs(self) -> list[ExtensionTab]:
        if not self._connected:
            return []
        await self._refresh_tabs()
        return [tab for tab in self._tabs if self._tab_is_accessible(tab)]

    async def _send_move_tab(self, tab_id: int, window_id: int, index: int) -> bool:
        """Send tab move request to the extension to restore original position."""
        if not self._connected or not self._ws:
            return False
        payload = {"tabId": tab_id, "windowId": window_id, "index": index}
        try:
            await self._send_request("move_tab", payload, timeout=2.0)
            return True
        except Exception as exc:
            logger.debug("Failed sending move_tab to extension: %s", exc)
            return False
