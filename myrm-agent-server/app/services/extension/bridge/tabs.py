"""[INPUT]
- .common (POS: shared primitives)

[OUTPUT]
- TabsMixin

[POS]
Extension bridge mixin: the mirror of the extension's tabs (including which ones the Agent owns and, for the ones its
pages opened, which Agent tab opened them), tab listing and tab-move requests.
"""

from __future__ import annotations

from .common import ExtensionTab
from .state import BridgeState


class TabsMixin(BridgeState):
    def _apply_tab_list(self, raw_tabs: object) -> None:
        """Replace the mirrored tabs with the extension's report; entries that are not well-formed tabs are skipped."""
        if not isinstance(raw_tabs, list):
            return
        tabs: list[ExtensionTab] = []
        agent_tabs: dict[int, int | None] = {}
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
                opener = item.get("openerTabId")
                agent_tabs[tab_id] = opener if isinstance(opener, int) else None
        self._tabs = tabs
        self._agent_tabs = agent_tabs

    async def list_tabs(self) -> list[ExtensionTab]:
        if not self._connected:
            return []
        await self._refresh_tabs()
        return [tab for tab in self._tabs if self._tab_is_accessible(tab)]
