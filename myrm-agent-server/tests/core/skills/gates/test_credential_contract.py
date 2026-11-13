"""Contract: a skill is listed exactly when the turn it is listed for can obtain the credential it declares.

[INPUT]
app.core.skills.gates.oauth_availability::IntegrationOAuthSkillBackend, apply_integration_oauth_availability (the verdict, both entry points)
app.core.channel_bridge.config_loader::load_user_configs (the inputs every turn hands the assembler)
app.services.agent.session_credential_assembler::assemble_session_credentials (what a turn is actually handed)
tests.support.skill_credential_store (stored credential states, the prebuilt skills as shipped)

[OUTPUT]
6 stored credential states x the 3 shipped skills that declare an OAuth issuer x 2 credential tracks = 36 cells. In
each cell the runtime backend, the catalog, and the written table of listed cells below agree, and so does the
turn: the issuers it is handed are the ones the skill declares exactly in the listed cells. Every unlisted cell
carries the reason text its Settings page shows.

[POS]
Listing and injection share one rule: an xAI provider key saved in Models & Providers lists x-live-search, and a
team-shared turn is never told about a skill whose credential it cannot get. The listed cells are written out here,
not derived from the gate, so a verdict that hides everything cannot pass. The runtime, the loader inputs and the
assembler are the production ones; only the database is in memory.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.agent.security import CredentialTrack
from myrm_agent_harness.backends.skills.memory import InMemorySkillBackend
from myrm_agent_harness.backends.skills.types import SkillMetadata

from app.core.channel_bridge import config_readiness
from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.core.channel_bridge.config_loader import load_user_configs
from app.core.skills.gates.oauth_availability import (
    GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE,
    X_LIVE_SEARCH_UNAVAILABLE,
    IntegrationOAuthSkillBackend,
    apply_integration_oauth_availability,
)
from app.core.skills.models import Skill
from app.services.agent.session_credential_assembler import assemble_session_credentials
from tests.support.skill_credential_store import (
    CredentialState,
    CredentialStore,
    issuer_declaring_prebuilt_skills,
    prebuilt_catalog_skill,
    prebuilt_skill_metadata,
)

PERSONAL = CredentialTrack.PERSONAL
SHARED = CredentialTrack.SHARED

# What each install has stored. A: only an xAI key in Models & Providers. B: only SuperGrok. C: both. D: nothing.
# E: only Google. F: SuperGrok plus an xAI provider row that holds no key.
_STATES: dict[str, CredentialState] = {
    "A": CredentialState(xai_provider="key"),
    "B": CredentialState(supergrok=True),
    "C": CredentialState(xai_provider="key", supergrok=True),
    "D": CredentialState(),
    "E": CredentialState(google=True),
    "F": CredentialState(xai_provider="no-key", supergrok=True),
}

# The shipped skills that declare an OAuth issuer, with what each declares.
_DECLARED = issuer_declaring_prebuilt_skills()

# The cells where the skill is listed. A team-shared turn never holds an owner's credential, so it lists none.
_LISTED: frozenset[tuple[str, str, CredentialTrack]] = frozenset(
    {
        ("A", "x-live-search", PERSONAL),
        ("B", "x-live-search", PERSONAL),
        ("C", "x-live-search", PERSONAL),
        ("F", "x-live-search", PERSONAL),
        ("E", "google-workspace", PERSONAL),
        ("E", "meeting-minutes-extractor", PERSONAL),
    }
)

# What an unlisted skill says on its Settings page; the last one is the text any other declared issuer gets.
_REASON: dict[str, str] = {
    "x-live-search": X_LIVE_SEARCH_UNAVAILABLE,
    "google-workspace": GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE,
    "meeting-minutes-extractor": "Connect google_workspace in Settings → Integrations → Credentials (required by skill)",
}


def _runtime_backend(*names: str, track: CredentialTrack = PERSONAL) -> IntegrationOAuthSkillBackend:
    """The agent runtime's gate over fresh copies of the shipped skills."""
    base = InMemorySkillBackend(skills=[prebuilt_skill_metadata(name) for name in names])
    return IntegrationOAuthSkillBackend(base, credential_track=track)


async def _runtime_skill(name: str, track: CredentialTrack) -> SkillMetadata:
    [skill] = await _runtime_backend(name, track=track).list_skills()
    return skill


async def _catalog_skill(credentials: CredentialStore, name: str, track: CredentialTrack) -> Skill:
    skill = prebuilt_catalog_skill(name)
    async with credentials.sessions() as db:
        await apply_integration_oauth_availability([skill], db, credential_track=track)
    return skill


async def _turn_issuers(track: CredentialTrack) -> frozenset[str]:
    """The issuers whose token a turn on ``track`` is handed: the production loader's inputs through the assembler."""
    invalidate_user_configs_cache()
    configs = await load_user_configs()
    assert configs is not None
    handed = await assemble_session_credentials(
        oauth_credentials_dict=configs.oauth_credentials_dict,
        providers_dict=configs.providers_dict,
        channel=None,
        credential_track=track,
    )
    return frozenset(credential.issuer for credential in handed if credential.token)


def test_the_contract_covers_every_shipped_skill_that_declares_an_oauth_issuer() -> None:
    """A new skill that declares an issuer must get its cells and its reason text here, not slip past."""
    assert set(_DECLARED) == set(_REASON)
    assert {issuer for issuers in _DECLARED.values() for issuer in issuers} == {"xai", "google_workspace"}
    assert {skill for _, skill, _ in _LISTED} <= set(_DECLARED)


@pytest.mark.parametrize("track", [PERSONAL, SHARED], ids=lambda track: track.value)
@pytest.mark.parametrize("skill", sorted(_DECLARED))
@pytest.mark.parametrize("state", sorted(_STATES))
async def test_a_skill_is_listed_exactly_when_the_turn_holds_the_credential_it_declares(
    credentials: CredentialStore, state: str, skill: str, track: CredentialTrack
) -> None:
    await credentials.seed(_STATES[state])
    listed = (state, skill, track) in _LISTED

    turn_holds_it = set(_DECLARED[skill]) <= await _turn_issuers(track)
    runtime = await _runtime_skill(skill, track)
    catalog = await _catalog_skill(credentials, skill, track)

    assert (turn_holds_it, runtime.available, catalog.available) == (listed, listed, listed)
    reason = None if listed else _REASON[skill]
    assert (runtime.unavailable_reason, catalog.unavailable_reason) == (reason, reason)


@pytest.mark.parametrize("track", [PERSONAL, SHARED], ids=lambda track: track.value)
async def test_loading_skills_by_id_gives_the_verdict_listing_them_gives(
    credentials: CredentialStore, track: CredentialTrack
) -> None:
    await credentials.seed(CredentialState(xai_provider="key", google=True))
    names = sorted(_DECLARED)

    listed = {skill.name: skill.available for skill in await _runtime_backend(*names, track=track).list_skills()}
    loaded = {skill.name: skill.available for skill in await _runtime_backend(*names, track=track).load_skills(names)}

    assert listed == loaded == dict.fromkeys(names, track is PERSONAL)


async def test_a_gate_built_without_a_track_judges_the_personal_track(credentials: CredentialStore) -> None:
    await credentials.seed(CredentialState(google=True))
    base = InMemorySkillBackend(skills=[prebuilt_skill_metadata("google-workspace")])

    [skill] = await IntegrationOAuthSkillBackend(base).list_skills()

    assert skill.available is True


async def test_a_stored_account_with_an_empty_token_does_not_list_its_skill(credentials: CredentialStore) -> None:
    """An entry whose token is empty is no connection, as for every other reader of the stored accounts."""
    await credentials.store_oauth({"google_workspace": {"token": "", "refresh_token": "refresh"}})

    [skill] = await _runtime_backend("google-workspace").list_skills()

    assert (skill.available, skill.unavailable_reason) == (False, GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE)


async def test_stored_providers_are_read_only_for_a_batch_that_declares_xai(
    credentials: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reading providers loads the user config, which may refresh an expiring subscription token over the network."""
    await credentials.seed(CredentialState(xai_provider="key", google=True))
    reads: list[None] = []
    read_providers = config_readiness.load_readiness_inputs

    async def counting_read() -> tuple[dict[str, object] | None, bool]:
        reads.append(None)
        return await read_providers()

    monkeypatch.setattr(config_readiness, "load_readiness_inputs", counting_read)

    await _runtime_backend("google-workspace", "meeting-minutes-extractor").list_skills()
    assert reads == []

    await _runtime_backend("x-live-search", "google-workspace", "meeting-minutes-extractor").list_skills()
    assert len(reads) == 1
