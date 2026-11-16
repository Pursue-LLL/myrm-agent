"""The providers the .env import fills must match the settings catalog and the transport's key variables.

[POS]
tests/architecture/test_importable_providers_catalog_parity.py

[INPUT]
- app.services.migration.env_secrets: `IMPORTABLE_PROVIDERS`, `ENV_TO_PROVIDER_ID`
- myrm_agent_harness transport `PROFILES`: the key variables and default endpoint of each provider
- myrm-agent-frontend providerCatalog.ts: the settings list's provider ids and display names

[OUTPUT]
- Fails when the list names a provider the settings list does not have or names it differently, when it reads a
  variable the transport does not read for that provider, or when a provider a key alone makes usable is left out
"""

from __future__ import annotations

import re

from myrm_agent_harness.toolkits.llms.transport.profile import PROFILES

from app.services.migration.env_secrets import ENV_TO_PROVIDER_ID, IMPORTABLE_PROVIDERS
from tests.support.frontend_api_paths import FRONTEND_SRC

_CATALOG = FRONTEND_SRC / "store" / "config" / "providerCatalog.ts"
_ENTRY_RE = re.compile(r"^  \w+: \{\n    id: '(?P<id>\w+)',\n    name: '(?P<name>[^']+)',", re.MULTILINE)
# A gateway the OpenAI wire reaches at a fixed endpoint: it has no transport profile, so its variables are named by hand.
_PROFILELESS = frozenset({"vercel_ai_gateway"})


def _catalog() -> dict[str, str]:
    entries = {match["id"]: match["name"] for match in _ENTRY_RE.finditer(_CATALOG.read_text(encoding="utf-8"))}
    assert entries, "no provider entries found in providerCatalog.ts"
    return entries


def _key_only_in_catalog() -> set[str]:
    """Catalog providers with a transport profile that holds a default endpoint and key variables."""
    return {
        provider_id
        for provider_id in _catalog()
        if (profile := PROFILES.get(provider_id)) is not None and profile.base_url and profile.api_key_env
    }


def test_every_importable_provider_is_in_the_settings_list_under_the_same_name() -> None:
    catalog = _catalog()

    assert {pid: name for pid, name in IMPORTABLE_PROVIDERS.items() if catalog.get(pid) != name} == {}


def test_every_variable_read_belongs_to_the_provider_it_fills() -> None:
    own_variables = {
        env: provider_id
        for provider_id in IMPORTABLE_PROVIDERS
        if provider_id in PROFILES
        for env in PROFILES[provider_id].api_key_env
    }

    assert {env: pid for env, pid in own_variables.items() if ENV_TO_PROVIDER_ID[env] != pid} == {}
    assert set(ENV_TO_PROVIDER_ID.values()) <= set(IMPORTABLE_PROVIDERS)


def test_a_provider_a_key_alone_makes_usable_is_never_left_out() -> None:
    assert _key_only_in_catalog() == set(IMPORTABLE_PROVIDERS) - _PROFILELESS
