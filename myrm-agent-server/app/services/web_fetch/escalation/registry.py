"""Build L4 provider chain from user config and search services.

[INPUT]
- app.schemas.config::WebFetchEscalationConfigValue (POS: User escalation config)
- app.services.web_fetch.providers (POS: Jina/Firecrawl provider implementations)

[OUTPUT]
- build_escalation_providers: Build ordered list of FetchEscalationProvider from user config.
- is_web_fetch_escalation_denied: Check if escalation is globally denied via env var.

[POS]
Registry that builds the L4 provider chain from user configuration.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.web_fetch.escalation.protocols import FetchEscalationProvider

from app.schemas.config import SearchServicesConfigValue, WebFetchEscalationConfigValue
from app.services.web_fetch.escalation.session_counter import session_escalation_counter
from app.services.web_fetch.providers.firecrawl import FirecrawlEscalationProvider
from app.services.web_fetch.providers.jina import JinaEscalationProvider

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def is_web_fetch_escalation_denied() -> bool:
    return os.getenv("MYRM_WEB_FETCH_ESCALATION", "").strip().lower() == "denied"


def resolve_firecrawl_api_key(
    cfg: WebFetchEscalationConfigValue,
    search_services: SearchServicesConfigValue | None,
) -> str | None:
    explicit = (cfg.firecrawl.api_key or "").strip()
    if explicit:
        return explicit
    if not cfg.firecrawl.inherit_from_search or search_services is None:
        return None
    for item in search_services.searchServiceConfigs:
        if item.search_service == "firecrawl" and item.enabled and item.api_key:
            return item.api_key.strip()
    return None


class SessionCappedEscalationProvider:
    """Wrap a provider with per-session attempt cap."""

    def __init__(
        self,
        inner: FetchEscalationProvider,
        *,
        session_id: str,
        session_cap: int,
    ) -> None:
        self._inner = inner
        self._session_id = session_id
        self._session_cap = session_cap
        self.provider_id = inner.provider_id

    async def fetch_url(self, url: str, *, max_chars: int = 0):
        if not session_escalation_counter.try_acquire(self._session_id, self._session_cap):
            logger.info(
                "Web fetch escalation session cap reached (%d) for session %s",
                self._session_cap,
                self._session_id,
            )
            return None
        return await self._inner.fetch_url(url, max_chars=max_chars)


async def load_web_fetch_escalation_config() -> WebFetchEscalationConfigValue | None:
    if is_web_fetch_escalation_denied():
        return None
    try:
        from app.services.config.service import config_service

        record = await config_service.get("webFetchEscalation")
        if not record:
            return None
        cfg = WebFetchEscalationConfigValue.model_validate(record.value)
        if not cfg.enabled:
            return None
        return cfg
    except Exception as exc:
        logger.debug("Web fetch escalation config unavailable: %s", exc)
        return None


async def build_escalation_providers(session_id: str) -> list[FetchEscalationProvider] | None:
    cfg = await load_web_fetch_escalation_config()
    if cfg is None:
        return None

    search_services: SearchServicesConfigValue | None = None
    try:
        from app.services.config.service import config_service

        search_record = await config_service.get("searchServices")
        if search_record:
            search_services = SearchServicesConfigValue.model_validate(search_record.value)
    except Exception:
        pass

    providers: list[FetchEscalationProvider] = []
    jina = JinaEscalationProvider(api_key=cfg.jina_api_key)
    providers.append(
        SessionCappedEscalationProvider(jina, session_id=session_id, session_cap=cfg.session_cap)
    )

    firecrawl_key = resolve_firecrawl_api_key(cfg, search_services)
    if firecrawl_key:
        firecrawl = FirecrawlEscalationProvider(firecrawl_key)
        providers.append(
            SessionCappedEscalationProvider(firecrawl, session_id=session_id, session_cap=cfg.session_cap)
        )

    return providers
