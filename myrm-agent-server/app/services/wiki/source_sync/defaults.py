"""Default wiki source sync settings applied after Google OAuth connect.

[INPUT]
- app.services.integrations.oauth_store::is_oauth_issuer_connected (POS: OAuth connection probe)
- app.services.wiki.source_sync.config_store (POS: wikiSourceSync UserConfig persistence)

[OUTPUT]
- maybe_enable_wiki_gmail_on_google_connect: turn on Gmail read-later sync when newly connected

[POS]
Server SSOT for post-OAuth wiki ingest defaults. Shared by Second Brain preset and Google OAuth callback.
"""

from __future__ import annotations

import logging

from app.database.connection import get_session
from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER
from app.services.integrations.oauth_store import is_oauth_issuer_connected
from app.services.wiki.source_sync.config_store import (
    load_wiki_source_sync_config,
    save_wiki_source_sync_config,
    wiki_source_sync_config_exists,
)

logger = logging.getLogger(__name__)

_DEFAULT_GMAIL_LABEL = "ReadLater"


async def maybe_enable_wiki_gmail_on_google_connect(*, respect_existing_config: bool = False) -> bool:
    """Enable Gmail read-later sync when Google Workspace OAuth is connected.

    When ``respect_existing_config`` is True (OAuth reconnect path), skip if the user
    already has a saved wiki source config row — preserves an explicit Gmail-off choice.

    Returns True when gmail sync was turned on by this call.
    """
    async with get_session() as db:
        if not await is_oauth_issuer_connected(db, GOOGLE_WORKSPACE_ISSUER):
            return False
        if respect_existing_config and await wiki_source_sync_config_exists(db):
            return False
        config = await load_wiki_source_sync_config(db)
        if config.gmail_enabled:
            return False
        await save_wiki_source_sync_config(
            db,
            config.model_copy(update={"gmail_enabled": True, "gmail_label": _DEFAULT_GMAIL_LABEL}),
        )
        logger.info("Wiki source sync: enabled Gmail label %s after Google OAuth connect", _DEFAULT_GMAIL_LABEL)
        return True
