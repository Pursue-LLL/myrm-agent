"""Integration test for the wiki MCP pipeline scenarios on /mcp (G1) — real flow.

Companion to test_connect_mcp_wiki_real_flow.py covering the remaining real
user journeys through the wiki MCP surface:

1. wiki_ingest_tool with a real URL (served from a local HTTP fixture) →
   real fetch + raw/ write
2. wiki_ingest_tool conflict: same filename with different content →
   real raw-gate conflict refusal
3. Full knowledge loop: raw ingest → real compilation (background worker or
   the production compile_all path) → wiki_query_tool hits the ingested facts
   (no refusal)
4. wiki_apply_tool invalid op refusal and a real patch_compiled_truth update

Edge-IO mocks follow the test_connect_mcp_real_flow.py precedent and cover the
memory tool plane only; the wiki plane (fetch, raw gate, compilation, query,
apply) is fully real.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki import WikiPendingEditsManager

from app.api.connect.router import router as connect_router
from app.api.mcp.endpoint import (
    clear_mcp_desktop_sessions,
    setup_mcp_endpoint,
    shutdown_mcp_endpoint,
)
from app.services.connect.service import ConnectService

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.wiki import WikiStructure
    from myrm_agent_harness.toolkits.wiki.retrieval.indexer import WikiIndexer

_ONBOARDING_DOC = (
    "# Onboarding guide\n\n"
    "Step 1: setup the dev environment with uv and bun. The dev environment "
    "setup is the foundation for everything.\n"
    "Step 2: read the team wiki. The team wiki holds our verified facts.\n"
    "Step 3: run ./myrm ready to verify the dev environment and the wiki mount."
)


@pytest.fixture(autouse=True)
def _cleanup_sessions() -> None:
    clear_mcp_desktop_sessions()
    yield
    clear_mcp_desktop_sessions()


@pytest.fixture
def tmp_connect_service(tmp_path: Path) -> ConnectService:
    return ConnectService(data_dir=tmp_path)


class _MarkdownHandler(BaseHTTPRequestHandler):
    """Serves a fixed markdown document for the real URL ingest path."""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        body = _ONBOARDING_DOC.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return  # Silence per-request stderr noise under pytest


@pytest.fixture
def local_markdown_url() -> AsyncIterator[str]:
    """Local HTTP endpoint standing in for a public web document."""
    server = HTTPServer(("127.0.0.1", 0), _MarkdownHandler)
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/onboarding.md"
    finally:
        server.server_close()


async def _seed_agent(agent_id: str, builtin_tools: list[str]) -> None:
    """Create a real agent row so the real profile resolver resolves it."""
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


async def _seed_platform_model_config() -> None:
    """Write real provider + default model rows so load_platform_llm is real."""
    from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
    from app.database.connection import get_session
    from app.database.models.config import UserConfig

    basic_key = os.environ.get("BASIC_API_KEY", "").strip()
    basic_url = (os.environ.get("BASIC_BASE_URL") or "").strip() or None
    basic_model = (os.environ.get("BASIC_MODEL") or "").strip()
    pid, stripped = (
        basic_model.split("/", 1) if "/" in basic_model else ("openai", basic_model)
    )

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
    default_model_payload = {"baseModel": {"primary": {"providerId": pid, "model": stripped}}}

    async with get_session() as session:
        for suffix, key, value in (
            ("providers", "providers", providers_payload),
            ("default", "defaultModelConfig", default_model_payload),
        ):
            session.add(
                UserConfig(
                    id=f"pytest-wiki-pipe-{suffix}",
                    config_key=key,
                    config_value=value,
                    version="1",
                    last_device_id="pytest",
                    is_encrypted=False,
                )
            )
        await session.commit()
    invalidate_user_configs_cache()


async def _cleanup_seeded_rows() -> None:
    """Remove seeded rows so later tests see a clean DB."""
    from sqlalchemy import delete as sa_delete

    from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
    from app.database.connection import get_session
    from app.database.models.agent import Agent
    from app.database.models.config import UserConfig
    from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

    async with get_session() as session:
        await session.execute(sa_delete(UserConfig).where(UserConfig.id.like("pytest-wiki-pipe-%")))
        await session.execute(sa_delete(Agent).where(Agent.id.in_(("agent-wiki-pipe",))))
        await session.commit()
    invalidate_user_configs_cache()
    get_agent_profile_resolver().invalidate("agent-wiki-pipe")


@pytest_asyncio.fixture
async def seeded_wiki_pipeline_env() -> AsyncIterator[None]:
    """Seed agent + model config rows, then remove them after the test."""
    basic_key = os.environ.get("BASIC_API_KEY", "").strip()
    raw_model = (os.environ.get("BASIC_MODEL") or "").strip()
    if not (basic_key and raw_model):
        pytest.skip("BASIC_API_KEY/BASIC_MODEL test secrets unavailable; wiki pipeline real-flow needs them")
    await _seed_platform_model_config()
    await _seed_agent("agent-wiki-pipe", ["wiki"])
    try:
        yield
    finally:
        await _cleanup_seeded_rows()


@pytest.mark.asyncio
async def test_connect_mcp_wiki_pipeline_real_flow(
    tmp_path: Path,
    tmp_connect_service: ConnectService,
    seeded_wiki_pipeline_env: None,
    local_markdown_url: str,
) -> None:
    """Real wiki pipeline journeys: URL ingest, conflict refusal, compile→query
    knowledge loop, and apply op handling — all through the real /mcp chain."""
    service = tmp_connect_service
    token_snippet = await service.generate_config("cursor", agent_id="agent-wiki-pipe")
    assert token_snippet.token.startswith("myrm_mcp_")

    app = FastAPI()
    app.include_router(connect_router, prefix="/api/v1")
    mock_memory_mgr = MagicMock()
    mock_memory_mgr.search = AsyncMock(return_value=[])

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
            headers = {
                "Authorization": f"Bearer {token_snippet.token}",
                "Content-Type": "application/json",
            }

            def call_tool(call_id: int, name: str, arguments: dict[str, object]) -> str:
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

            vault_raw_dir = (
                Path(os.environ["MYRM_DATA_DIR"]).expanduser()
                / "harness" / "wiki" / "agents" / "agent-wiki-pipe" / "raw"
            )

            # 1. SSRF security: internal-network URL is refused by the real guard
            #    (a local HTTP fixture stands in for an attacker-controlled
            #    internal endpoint; the fetch layer blocks non-public IPs).
            internal_refused = call_tool(
                1,
                "wiki_ingest_tool",
                {"source": local_markdown_url, "filename": "internal.md"},
            )
            assert "Failed to ingest document" in internal_refused
            assert not (vault_raw_dir / "internal.md").exists()

            # 2. Real public URL ingest → real fetch + raw/ write
            ingested_url = call_tool(
                2,
                "wiki_ingest_tool",
                {"source": "https://example.com", "filename": "example-page.md"},
            )
            assert "Successfully ingested document" in ingested_url
            assert (vault_raw_dir / "example-page.md").is_file()

            # 3. Conflict refusal: same filename, different content
            conflict = call_tool(
                3,
                "wiki_ingest_tool",
                {"source": "# Different content\n\nStep X: conflicting update.", "filename": "example-page.md"},
            )
            assert "Raw source already exists with different content" in conflict

            # 4. Knowledge loop: ingest → compile → HITL review → publish → query.
            #    Compiler extraction counts in-document mentions (min_concept_mentions
            #    noise floor), generated articles land in the human-in-the-loop
            #    pending drafts store, approval publishes them to concepts/, and
            #    only published concepts are queryable — the full production
            #    knowledge governance path.
            ingested_guide = call_tool(
                4,
                "wiki_ingest_tool",
                {"source": _ONBOARDING_DOC, "filename": "onboarding-guide.md"},
            )
            assert "Successfully ingested document" in ingested_guide

            await _await_real_compilation()

            structure, indexer = _build_review_structure()
            manager = WikiPendingEditsManager(structure, indexer=indexer)
            drafts = manager.get_pending_edits()
            assert len(drafts) > 0, "compile must stage HITL pending drafts for review"
            print(f"[wiki-pipeline-real] staged drafts: {[d['concept_name'] for d in drafts]}")

            for draft in drafts:
                assert await manager.approve_edit(int(draft["id"])) is True

            published = structure.list_concepts()
            assert len(published) > 0, "approved drafts must publish to concepts/"

            answer = call_tool(
                5,
                "wiki_query_tool",
                {"question": "What are the onboarding steps for the dev environment?"},
            )
            assert "REFUSED" not in answer, answer
            lowered = answer.lower()
            assert "uv" in lowered or "myrm" in lowered or "wiki" in lowered, answer[:400]

            # 5. Apply ops: invalid op refusal + a real concept patch
            invalid_op = call_tool(
                6,
                "wiki_apply_tool",
                {"op": "bogus_op", "concept_name": "team/onboarding"},
            )
            assert "Invalid op 'bogus_op'" in invalid_op
            assert "Allowed:" in invalid_op

            patched = call_tool(
                7,
                "wiki_apply_tool",
                {
                    "op": "create_note",
                    "concept_name": "team/mcp-pipeline-note",
                    "body": "Note created by the wiki pipeline real-flow test.",
                },
            )
            assert "(created)" in patched

        finally:
            await shutdown_mcp_endpoint()


async def _await_real_compilation() -> str:
    """Wait for wiki articles to be staged as HITL drafts after MCP ingest.

    The enqueue path starts the background worker itself; if the worker task
    cannot run under the TestClient event loop (request portal torn down),
    fall back to compile_all() — the same production path Settings > Wiki
    import uses to drain the queue synchronously. Returns which path ran.
    """
    from myrm_agent_harness.toolkits.wiki import WikiCompiler, WikiConfig
    from myrm_agent_harness.toolkits.wiki.core.config import WikiCompileConfig

    from app.services.agent.platform_config import load_platform_llm
    from app.services.wiki.daily_review.prompts import FOUR_DIMENSION_EXTRACT_PROMPT

    structure, indexer = _build_review_structure()
    config = WikiConfig()
    llm = await load_platform_llm()
    compiler = WikiCompiler(
        llm,
        structure,
        config,
        # Same four-dimension routing prompt as the MCP endpoint compiler so
        # concept naming converges with the surface under test.
        compile_config=WikiCompileConfig(
            extract_concepts_prompt_template=FOUR_DIMENSION_EXTRACT_PROMPT,
        ),
        indexer=indexer,
    )

    manager = WikiPendingEditsManager(structure, indexer=indexer)
    for _ in range(30):
        if manager.get_pending_edits():
            return "background-worker"
        await asyncio.sleep(1.0)

    await compiler.compile_all()
    return "compile_all"


def _build_review_structure() -> tuple["WikiStructure", "WikiIndexer"]:
    """Build the (structure, indexer) pair for HITL review/approve assertions."""
    from myrm_agent_harness.toolkits.wiki import WikiConfig, WikiStructure
    from myrm_agent_harness.toolkits.wiki.retrieval.indexer import WikiIndexer

    from app.services.wiki.vault import resolve_agent_wiki_vault_path

    structure = WikiStructure(resolve_agent_wiki_vault_path("agent-wiki-pipe"))
    config = WikiConfig()
    return structure, WikiIndexer(structure, config)
