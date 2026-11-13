"""The skills catalog lists on an install that has no default model yet instead of failing.

[INPUT]
app.core.skills.gates.oauth_availability::apply_integration_oauth_availability (real credential verdict)
app.core.channel_bridge.config_readiness::load_readiness_inputs (reads the stored provider bundle)
tests.support.skill_credential_store::credentials (the stored provider rows and OAuth tokens)

[OUTPUT]
That a fresh install gets x-live-search marked unavailable, and that an xAI provider saved before any default model
keeps it available, both without an error from the config loader that refuses to answer without a default model.

[POS]
Real ORM tables on an in-memory database: it is what every first launch of the desktop app looks like.
"""

from __future__ import annotations

import pytest

from app.core.skills.gates.oauth_availability import X_LIVE_SEARCH_UNAVAILABLE, apply_integration_oauth_availability
from tests.support.skill_credential_store import CredentialState, CredentialStore, prebuilt_catalog_skill


async def _list_x_live_search(credentials: CredentialStore) -> tuple[bool, str | None]:
    skill = prebuilt_catalog_skill("x-live-search")
    async with credentials.sessions() as db:
        await apply_integration_oauth_availability([skill], db)
    return skill.available, skill.unavailable_reason


@pytest.mark.asyncio
async def test_a_fresh_install_lists_x_live_search_as_unavailable(credentials: CredentialStore) -> None:
    assert await _list_x_live_search(credentials) == (False, X_LIVE_SEARCH_UNAVAILABLE)


@pytest.mark.asyncio
async def test_providers_saved_without_a_default_model_but_with_xai_keep_x_live_search_available(
    credentials: CredentialStore,
) -> None:
    await credentials.seed(CredentialState(xai_provider="key"), default_model=False)

    assert await _list_x_live_search(credentials) == (True, None)


@pytest.mark.asyncio
async def test_providers_saved_without_a_default_model_and_without_xai_leave_it_unavailable(
    credentials: CredentialStore,
) -> None:
    await credentials.seed(CredentialState(), default_model=False)

    assert await _list_x_live_search(credentials) == (False, X_LIVE_SEARCH_UNAVAILABLE)
