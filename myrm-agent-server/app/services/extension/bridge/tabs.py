"""[INPUT]
- .common (POS: shared primitives)

[OUTPUT]
- TabsMixin

[POS]
Extension bridge mixin: the mirror of the extension's tabs (including which ones the Agent opened), tab listing and
tab-move requests.
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
    def _apply_tab_list(self, raw_tabs: object) -> None:
        """Replace the mirrored tabs with the extension's report; entries that are not well-formed tabs are skipped."""
        if not isinstance(raw_tabs, list):
            return
        tabs: list[ExtensionTab] = []
        agent_tab_ids: set[int] = set()
        for item in raw_tabs:
            tab_id = item.get("id") if isinstance(item, dict) else None
            if not isinstance(tab_id, int):
                continue
            tabs.append(
                ExtensionTab(
                    tab_id=tab_id,
                    url=str(item.get("url") or ""),
                    title=str(item.get("title") or ""),
                    domain=str(item.get("domain") or ""),
                    active=item.get("active") is True,
                )
            )
            if item.get("agentOwned") is True:
                agent_tab_ids.add(tab_id)
        self._tabs = tabs
        self._agent_tab_ids = frozenset(agent_tab_ids)

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
