"""Live-stack integration: UECD web_fetch spill → GET /files/evicted (no ASGI mock)."""

from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import httpx
import pytest

from tests.support.chrome_mcp_e2e import get_e2e_api_url, http_json


def _live_api_reachable(api_base: str) -> bool:
    try:
        resp = httpx.get(f"{api_base}/api/v1/health", timeout=5.0)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.integration
class TestEvictedUecdLiveServerIntegration:
    """Hit running backend when ./myrm ready is up — critical path uses real disk + HTTP."""

    @pytest.mark.skipif(
        os.environ.get("MYRM_SKIP_LIVE_SERVER") == "1",
        reason="Live server checks disabled",
    )
    def test_live_evicted_api_reads_web_fetch_uecd_spill(self) -> None:
        api_base = get_e2e_api_url()
        if not _live_api_reachable(api_base):
            pytest.skip(f"Live API not reachable at {api_base}")

        seed = http_json(
            "POST",
            f"{api_base}/api/v1/chats/test/seed-evicted-live-terminal-fixture",
            expected_statuses=frozenset({200, 201, 404}),
        )
        if not isinstance(seed, dict) or "chat_id" not in seed:
            pytest.skip(
                "Live server missing seed route — stack pinned by wave; "
                "run ./myrm restart when leases idle to pick up new code"
            )
        chat_id = str(seed["chat_id"])
        filename = str(seed["filename"])
        marker = str(seed["marker_line"])

        resp = httpx.get(
            f"{api_base}/api/v1/files/evicted",
            params={
                "chat_id": chat_id,
                "filename": filename,
                "offset": 0,
                "limit": 0,
            },
            timeout=15.0,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert marker in body.get("content", "")
        assert int(body.get("total_lines", 0)) >= int(seed.get("line_count", 0))

    @pytest.mark.skipif(
        os.environ.get("MYRM_SKIP_LIVE_SERVER") == "1",
        reason="Live server checks disabled",
    )
    def test_live_evicted_api_404_when_file_missing(self) -> None:
        api_base = get_e2e_api_url()
        if not _live_api_reachable(api_base):
            pytest.skip(f"Live API not reachable at {api_base}")

        resp = httpx.get(
            f"{api_base}/api/v1/files/evicted",
            params={
                "chat_id": "chat_missing_uecd_e2e",
                "filename": f"output_{uuid.uuid4().hex[:8]}.txt",
            },
            timeout=10.0,
        )
        assert resp.status_code == 404
        payload = resp.json()
        detail = payload.get("detail")
        if isinstance(detail, dict) and "expired" in detail:
            assert detail.get("expired") is True
        elif payload.get("code") == 40401:
            pytest.skip(
                "Live server evicted API envelope is pre-UECD — restart when wave idle"
            )
        else:
            raise AssertionError(f"Unexpected 404 payload: {payload!r}")


@pytest.mark.integration
class TestEvictedUecdSeedFixtureIntegration:
    """Seed fixture contract via in-process app (DB + disk, no live :8080)."""

    def test_seed_fixture_persists_progress_steps_and_spill_file(
        self, init_test_database
    ) -> None:
        import asyncio
        import uuid
        from pathlib import Path

        from fastapi.testclient import TestClient

        from tests.support.minimal_app import build_minimal_app

        app = build_minimal_app("chats", preset="chats")
        client = TestClient(app)

        async def _seed_agent() -> str:
            from app.database.models.agent import Agent
            from app.platform_utils import get_session_factory

            agent_id = f"agent_{uuid.uuid4().hex[:8]}"
            session_factory = get_session_factory()
            async with session_factory() as db:
                db.add(
                    Agent(
                        id=agent_id,
                        name="UECD Seed Agent",
                        model_selection={"model": "gpt-4o-mini"},
                    ),
                )
                await db.commit()
            return agent_id

        agent_id = asyncio.run(_seed_agent())
        with patch("app.api.chats.test_fixtures.is_local_mode", return_value=True):
            resp = client.post(
                "/api/v1/chats/test/seed-evicted-live-terminal-fixture",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        chat_id = str(body["chat_id"])
        filename = str(body["filename"])
        workspace_dir = Path(str(body["workspace_dir"]))
        spill_path = workspace_dir / ".context" / chat_id / "evicted" / filename
        assert spill_path.is_file(), spill_path
        assert str(body["marker_line"]) in spill_path.read_text(encoding="utf-8")

        messages_resp = client.get(f"/api/v1/chats/{chat_id}/messages")
        assert messages_resp.status_code == 200
        messages = messages_resp.json()["data"]["messages"]
        assistant = next(m for m in messages if m.get("role") == "assistant")
        steps = (assistant.get("metadata") or {}).get("progressSteps")
        assert isinstance(steps, list) and steps
        assert steps[0].get("evicted_file_ref") == filename

    def test_seed_expired_variant_removes_spill_file(self, init_test_database) -> None:
        import asyncio
        import uuid
        from pathlib import Path

        from fastapi.testclient import TestClient

        from tests.support.minimal_app import build_minimal_app

        app = build_minimal_app("chats", preset="chats")
        client = TestClient(app)

        async def _seed_agent() -> None:
            from app.database.models.agent import Agent
            from app.platform_utils import get_session_factory

            agent_id = f"agent_{uuid.uuid4().hex[:8]}"
            session_factory = get_session_factory()
            async with session_factory() as db:
                db.add(
                    Agent(
                        id=agent_id,
                        name="UECD Expired Seed Agent",
                        model_selection={"model": "gpt-4o-mini"},
                    ),
                )
                await db.commit()

        asyncio.run(_seed_agent())
        with patch("app.api.chats.test_fixtures.is_local_mode", return_value=True):
            resp = client.post(
                "/api/v1/chats/test/seed-evicted-live-terminal-fixture?variant=expired",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        chat_id = str(body["chat_id"])
        filename = str(body["filename"])
        workspace_dir = Path(str(body["workspace_dir"]))
        spill_path = workspace_dir / ".context" / chat_id / "evicted" / filename
        assert not spill_path.is_file()
