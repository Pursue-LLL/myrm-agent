"""Integration test for the wiki MCP surface on /mcp (G1) — real flow.

Real (un-mocked) wiki chain through the MCP endpoint:
1. Seed real agents in DB — one with enabled_builtin_tools=["wiki"], one without
2. Seed real platform model config in DB UserConfig (providers + defaultModelConfig)
   from BASIC_* test env so load_platform_llm resolves a real LLM
3. Real token generation via ConnectService
4. /mcp tools/list: wiki tools visible only for the wiki-enabled agent token
5. /mcp tools/call real invocations:
   - wiki_query_tool on an empty vault → real engine refusal (REFUSED)
   - wiki_ingest_tool with an existing local file path → trusted-surface refusal
   - wiki_ingest_tool with raw text → real raw/ write on disk + compilation queue
   - wiki_apply_tool create_note → real concept note creation on disk
6. Real-LLM segment: bind the wiki_query_tool MCP proxy to the real model, let
   the model decide the tool call, then execute it through /mcp

Edge-IO mocks follow the test_connect_mcp_real_flow.py precedent and cover the
memory tool plane only (_require_embedding_config + create_memory_manager);
the wiki plane itself (profile resolution, vault paths, engine construction,
tool invocation) is fully real.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.connect.router import router as connect_router
from app.api.mcp.endpoint import (
    clear_mcp_desktop_sessions,
    setup_mcp_endpoint,
    shutdown_mcp_endpoint,
)
from app.services.connect.service import ConnectService


@pytest.fixture(autouse=True)
def _cleanup_sessions() -> None:
    clear_mcp_desktop_sessions()
    yield
    clear_mcp_desktop_sessions()


@pytest.fixture
def tmp_connect_service(tmp_path: Path) -> ConnectService:
    return ConnectService(data_dir=tmp_path)


def _split_provider_prefix(model: str) -> tuple[str, str]:
    """Split 'provider/model' into (provider_id, model) with provider default."""
    if "/" in model:
        pid, name = model.split("/", 1)
        return pid.strip(), name.strip()
    return "openai", model.strip()


async def _seed_platform_model_config() -> None:
    """Write real provider + default model rows into user_configs (plain rows).

    Mirrors the WebUI Settings > Model Service payload so load_platform_llm()
    resolves the real BASIC_* test model through the same code path production
    uses (config_loader → _fallback_model_from_providers → ChatLiteLLM).
    """
    from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
    from app.database.connection import get_session
    from app.database.models.config import UserConfig

    basic_key = os.environ.get("BASIC_API_KEY", "").strip()
    basic_url = (os.environ.get("BASIC_BASE_URL") or "").strip() or None
    basic_model = (os.environ.get("BASIC_MODEL") or "").strip()
    pid, stripped = _split_provider_prefix(basic_model)

    providers_payload = {
        "providers": [
            {
                "id": pid,
                "providerType": pid,
                "isEnabled": True,
                "apiUrl": basic_url,
                "apiKeys": [{"key": basic_key, "isActive": True}],
                "enabledModels": [stripped],
            }
        ]
    }
    default_model_payload = {
        "baseModel": {"primary": {"providerId": pid, "model": stripped}}
    }

    async with get_session() as session:
        for suffix, key, value in (
            ("providers", "providers", providers_payload),
            ("default", "defaultModelConfig", default_model_payload),
        ):
            session.add(
                UserConfig(
                    id=f"pytest-wiki-real-{suffix}",
                    config_key=key,
                    config_value=value,
                    version="1",
                    last_device_id="pytest",
                    is_encrypted=False,
                )
            )
        await session.commit()
    invalidate_user_configs_cache()


async def _seed_agent(agent_id: str, builtin_tools: list[str]) -> None:
    """Create a real agent row so the real profile resolver resolves it.

    metadata.enabled_builtin_tools persists into tools_allowed (non-baseline
    ids survive), which is exactly the field the /mcp wiki gate reads.
    """
    from myrm_agent_harness.backends.profiles.types import AgentProfile

    from app.database.repositories.agent_repo import AgentRepository
    from app.platform_utils import get_session_factory
    from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

    session_factory = get_session_factory()
    async with session_factory() as session:
        await AgentRepository.create_profile(
            session,
            AgentProfile(
                id=agent_id,
                display_name=agent_id,
                metadata={"enabled_builtin_tools": builtin_tools},
            ),
        )
        await session.commit()
    get_agent_profile_resolver().invalidate(agent_id)


async def _cleanup_seeded_rows() -> None:
    """Remove seeded UserConfig/agent rows so later tests see a clean DB."""
    from sqlalchemy import delete as sa_delete

    from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
    from app.database.connection import get_session
    from app.database.models.agent import Agent
    from app.database.models.config import UserConfig
    from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

    async with get_session() as session:
        await session.execute(sa_delete(UserConfig).where(UserConfig.id.like("pytest-wiki-real-%")))
        await session.execute(sa_delete(Agent).where(Agent.id.in_(("agent-wiki", "agent-plain"))))
        await session.commit()
    invalidate_user_configs_cache()
    for agent_id in ("agent-wiki", "agent-plain"):
        get_agent_profile_resolver().invalidate(agent_id)


@pytest_asyncio.fixture
async def seeded_wiki_flow_env() -> AsyncIterator[None]:
    """Seed real agents + platform model config rows, then remove them after.

    Keeps the shared test DB clean for later tests that may rely on the
    "no providers configured" state (30s config cache + resolver cache are
    invalidated on both ends).
    """
    basic_key = os.environ.get("BASIC_API_KEY", "").strip()
    raw_model = (os.environ.get("BASIC_MODEL") or "").strip()
    if not (basic_key and raw_model):
        pytest.skip("BASIC_API_KEY/BASIC_MODEL test secrets unavailable; wiki real-flow needs them")
    await _seed_platform_model_config()
    await _seed_agent("agent-wiki", ["wiki"])
    await _seed_agent("agent-plain", [])
    try:
        yield
    finally:
        await _cleanup_seeded_rows()


@pytest.mark.asyncio
async def test_connect_mcp_wiki_real_flow(
    tmp_path: Path,
    tmp_connect_service: ConnectService,
    seeded_wiki_flow_env: None,
) -> None:
    """Full real cycle: DB-seeded agents + platform model config, tokens, wiki
    tool visibility per token, real wiki tool invocations, real-LLM tool call."""
    service = tmp_connect_service

    # Distinct profiles per token: connect state is keyed by profile id, so a
    # same-profile regeneration would revoke the earlier token (resolve_token
    # matches one state per profile).
    wiki_token_snippet = await service.generate_config("cursor", agent_id="agent-wiki")
    plain_token_snippet = await service.generate_config("claude_code", agent_id="agent-plain")
    assert wiki_token_snippet.token.startswith("myrm_mcp_")
    assert plain_token_snippet.token.startswith("myrm_mcp_")

    app = FastAPI()
    app.include_router(connect_router, prefix="/api/v1")

    mock_memory_mgr = MagicMock()
    mock_memory_mgr.search = AsyncMock(return_value=[])

    local_secret_file = tmp_path / "local-notes.md"
    local_secret_file.write_text("# local secret notes\ninternal only\n", encoding="utf-8")

    with (
        patch("app.services.connect.get_connect_service", return_value=service),
        patch("app.api.connect.router.get_connect_service", return_value=service),
        patch(
            "app.api.mcp.endpoint._require_embedding_config",
            AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.core.memory.adapters.setup.create_memory_manager",
            AsyncMock(return_value=mock_memory_mgr),
        ),
    ):
        await setup_mcp_endpoint(app)
        client = TestClient(app)

        try:
            headers_wiki = {
                "Authorization": f"Bearer {wiki_token_snippet.token}",
                "Content-Type": "application/json",
            }
            headers_plain = {
                "Authorization": f"Bearer {plain_token_snippet.token}",
                "Content-Type": "application/json",
            }
            rpc_list_tools = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}

            # 1. Wiki-enabled token sees the three wiki tools
            resp_wiki = client.post("/mcp", headers=headers_wiki, json=rpc_list_tools)
            assert resp_wiki.status_code == 200
            names_wiki = [t["name"] for t in resp_wiki.json().get("result", {}).get("tools", [])]
            assert {"wiki_query_tool", "wiki_ingest_tool", "wiki_apply_tool"} <= set(names_wiki)
            assert "memory_recall" in names_wiki

            # 2. Wiki-disabled token sees no wiki tools at all
            resp_plain = client.post("/mcp", headers=headers_plain, json=rpc_list_tools)
            assert resp_plain.status_code == 200
            names_plain = [t["name"] for t in resp_plain.json().get("result", {}).get("tools", [])]
            assert "memory_recall" in names_plain
            assert not any(name.startswith("wiki_") for name in names_plain)

            def call_tool(headers: dict[str, str], call_id: int, name: str, arguments: dict[str, object]) -> str:
                rpc = {
                    "jsonrpc": "2.0",
                    "id": call_id,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
                resp = client.post("/mcp", headers=headers, json=rpc)
                assert resp.status_code == 200
                content = resp.json().get("result", {}).get("content", [])
                assert len(content) == 1
                return content[0]["text"]

            # 3. Real wiki_query on an empty vault → real engine refusal
            refused = call_tool(headers_wiki, 2, "wiki_query_tool", {"question": "How does the team onboard new members?"})
            assert "REFUSED" in refused
            assert "no verified basis" in refused

            # 4. Real wiki_ingest with an existing local file path → refused (trusted-surface narrowing)
            rejected = call_tool(
                headers_wiki,
                3,
                "wiki_ingest_tool",
                {"source": str(local_secret_file), "filename": "notes.md"},
            )
            assert "Rejected" in rejected
            assert "local file paths are not supported" in rejected

            # 5. Real wiki_ingest with raw text → real raw/ write on disk + compile queue
            ingested = call_tool(
                headers_wiki,
                4,
                "wiki_ingest_tool",
                {
                    "source": "# Onboarding guide\nStep 1: setup dev environment. Step 2: read the wiki.",
                    "filename": "onboarding-guide.md",
                },
            )
            assert "Successfully ingested document" in ingested
            assert "Compilation queued" in ingested
            vault_raw = (
                Path(os.environ["MYRM_DATA_DIR"]).expanduser()
                / "harness" / "wiki" / "agents" / "agent-wiki" / "raw" / "onboarding-guide.md"
            )
            assert vault_raw.is_file()

            # 6. Real wiki_apply create_note → real concept note creation on disk
            applied = call_tool(
                headers_wiki,
                5,
                "wiki_apply_tool",
                {
                    "op": "create_note",
                    "concept_name": "mcp-e2e/real-flow-note",
                    "body": "Real-flow created note via MCP wiki_apply_tool.",
                },
            )
            assert "(created)" in applied

            # 7. Real-LLM segment: model decides to call wiki_query_tool, executed through /mcp
            basic_key = os.environ.get("BASIC_API_KEY", "").strip()
            raw_model = (os.environ.get("BASIC_MODEL") or "").strip()
            from langchain_core.messages import HumanMessage
            from langchain_core.tools import StructuredTool
            from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model

            from tests.api.agent.utils import _convert_litellm_model

            base_url = (os.environ.get("BASIC_BASE_URL") or "").strip() or None
            llm = create_litellm_model(
                model=_convert_litellm_model(raw_model),
                api_key=basic_key,
                base_url=base_url,
                temperature=0,
            )

            async def mcp_wiki_query_proxy(question: str) -> str:
                return call_tool(headers_wiki, 99, "wiki_query_tool", {"question": question})

            wiki_query_proxy = StructuredTool.from_function(
                coroutine=mcp_wiki_query_proxy,
                name="wiki_query_tool",
                description="Query the personal wiki knowledge base for verified team facts and concepts.",
            )

            llm_with_tools = llm.bind_tools([wiki_query_proxy])
            ai_msg = await llm_with_tools.ainvoke(
                [HumanMessage(content="Please search the wiki knowledge base for the onboarding steps.")]
            )
            assert ai_msg.tool_calls is not None
            assert len(ai_msg.tool_calls) > 0
            assert ai_msg.tool_calls[0]["name"] == "wiki_query_tool"
            print(f"[Real-LLM MCP Wiki Test] Model {raw_model} issued tool call: {ai_msg.tool_calls[0]['name']}")

            proxy_args = dict(ai_msg.tool_calls[0]["args"])
            llm_result = await mcp_wiki_query_proxy(question=str(proxy_args.get("question", "")))
            assert "REFUSED" in llm_result or "onboarding" in llm_result.lower()
            print(f"[Real-LLM MCP Wiki Test] MCP endpoint executed the model's tool call: {llm_result[:120]}")

        finally:
            await shutdown_mcp_endpoint()
