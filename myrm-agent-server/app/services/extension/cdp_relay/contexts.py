"""Virtual browser contexts: ownership groups for the tabs one Playwright client opens.

[INPUT]
- cdp_relay.targets::TargetRegistry (POS: tab mirror, close, background work)
- cdp_relay.models::CdpClient (POS: relay state records)

[OUTPUT]
- ContextRegistry: create / dispose contexts, dispose a disconnected client's contexts

[POS]
Playwright's new_context() needs Target.createBrowserContext. The relay serves it over the user's one real
browser: a context groups the tabs the Agent opens (closed together on dispose or client disconnect) and
shares the browser's cookies and storage. It is not an isolated profile.
"""

from __future__ import annotations

import logging

from .models import CdpClient
from .targets import TargetRegistry

logger = logging.getLogger(__name__)


class ContextRegistry(TargetRegistry):
    """Tracks which client created which virtual context and closes a context's tabs when it ends."""

    def __init__(self) -> None:
        super().__init__()
        self._contexts: dict[str, CdpClient] = {}
        self._next_context_ordinal = 1

    def _create_context(self, owner: CdpClient) -> str:
        context_id = f"myrm-ctx-{self._next_context_ordinal}"
        self._next_context_ordinal += 1
        self._contexts[context_id] = owner
        return context_id

    async def _dispose_context(self, context_id: str) -> None:
        """Forget the context and close the tabs opened in it; a tab the extension will not close joins the default context."""
        self._contexts.pop(context_id, None)
        for tab_id, tab in list(self._tabs.items()):
            if tab.context_id != context_id or self._tabs.get(tab_id) is not tab:
                continue
            try:
                await self._close_tab(tab_id)
            except RuntimeError as exc:
                logger.warning("Could not close tab %s of disposed browser context %s: %s", tab_id, context_id, exc)
                tab.context_id = None

    def _dispose_contexts_of(self, client: CdpClient) -> None:
        """A context never outlives the connection that created it."""
        for context_id, owner in list(self._contexts.items()):
            if owner is client:
                self._spawn(self._dispose_context(context_id))
