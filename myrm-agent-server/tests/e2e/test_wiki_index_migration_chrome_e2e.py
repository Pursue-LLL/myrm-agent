"""Private-runtime E2E: a vault indexed under an older page identity is migrated when the running server opens it.

A user who upgrades keeps the wiki index built by the previous version. The test writes an agent's vault the way the
harness does, leaves its index as the previous version held it (a page keyed by its compile name, an old
``user_version``), and then asks the running server for the page through the wiki API, the request the frontend's wiki service sends for a concept search.
The index must come back keyed by the page's file name, stamped with the current version, and answer the search.
"""

from __future__ import annotations

import shutil
import uuid

import pytest
from myrm_agent_harness.toolkits.wiki.retrieval.identity_migration import INDEX_SCHEMA_VERSION

from tests.support.chrome_mcp_e2e import get_e2e_api_url, http_json
from tests.support.knowledge_pack_chrome import (
    agent_vault_dir,
    build_indexed_vault,
    create_agent,
    downgrade_index_to_legacy,
    index_state,
)

_SKILL_PAGE = "SKILL.md"
_SKILL_KEY = "skillmd"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_legacy_index_is_migrated_when_the_server_opens_the_agent_vault() -> None:
    api_url = get_e2e_api_url()
    suffix = uuid.uuid4().hex[:8]
    agent_id = create_agent(api_url, suffix)
    vault_dir = agent_vault_dir(api_url, agent_id)
    try:
        build_indexed_vault(vault_dir, {_SKILL_PAGE: f"The Meridian crew handover note {suffix} lives on this page."})
        assert index_state(vault_dir) == (frozenset({_SKILL_KEY}), INDEX_SCHEMA_VERSION)

        downgrade_index_to_legacy(vault_dir, {_SKILL_KEY: _SKILL_PAGE})
        assert index_state(vault_dir) == (frozenset({_SKILL_PAGE}), 3), "the legacy index was not left as the old version held it"

        found = http_json("GET", f"{api_url}/api/v1/wiki/concepts?agent_id={agent_id}&query={suffix}")
        assert isinstance(found, dict), found
        assert found["concepts"] == [_SKILL_KEY], found
        assert index_state(vault_dir) == (frozenset({_SKILL_KEY}), INDEX_SCHEMA_VERSION)
    finally:
        shutil.rmtree(vault_dir, ignore_errors=True)
