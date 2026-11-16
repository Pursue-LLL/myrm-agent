"""Chrome LIVE_AGENT E2E: structured clarify form Skip resumes agent (B-package).

Implementation modules: tests/e2e/clarify_skip/
"""

from __future__ import annotations

import asyncio
import os

import pytest
from cdp_chat.support import get_e2e_api_url, wait_e2e_provider_ready
from chrome_mcp.client import ChromeMcpClient

from tests.e2e.clarify_skip.flow import open_chat_session, run_flow
from tests.support.e2e_runtime_guard import E2EResourceLedger


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_clarify_skip_button_resumes_agent_in_real_chat(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Real WebUI: clarify ready via API pending or DOM Skip; resume via private API."""
    api_url = get_e2e_api_url()
    if not wait_e2e_provider_ready(api_url=api_url):
        pytest.fail(
            "Provider config not ready for live clarify Chrome E2E — run via ./myrm-dev test -m chrome_e2e "
            "after ./myrm-dev ready --chrome (API /api/v1/config/readiness provider.is_ready must be true)",
        )
    # Clarify skip assertions do not depend on shared search-service policy hydration.
    os.environ.pop("MYRM_E2E_SEARCH_POLICY", None)

    client = ChromeMcpClient(request_timeout_sec=120.0)
    await asyncio.to_thread(client.start)
    try:
        chat = await open_chat_session(client)
        chat_id = await run_flow(chat, e2e_resource_ledger)
        assert chat_id
    finally:
        await asyncio.to_thread(client.close)
