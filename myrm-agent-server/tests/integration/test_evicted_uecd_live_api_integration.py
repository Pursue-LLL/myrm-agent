"""Live-stack integration: UECD web_fetch spill → GET /files/evicted (no ASGI mock)."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

_DEV_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_DEV_LIB) not in sys.path:
    sys.path.insert(0, str(_DEV_LIB))


def _resolve_verify_api_base(*, ensure_backend: bool = True) -> str:
    """Epoch-matched API base for live server-route tests (parallel-safe, not shared :8080)."""
    from e2e_api_verify import monorepo_root, resolve_e2e_api_context  # noqa: PLC0415

    ctx = resolve_e2e_api_context()
    if ctx.blocked and ensure_backend:
        from verify_backend_seed import ensure_verify_backend_seed  # noqa: PLC0415

        seed = ensure_verify_backend_seed(monorepo=monorepo_root())
        if not seed.ok:
            pytest.skip(f"verify-api seed failed: {seed.detail}")
        ctx = resolve_e2e_api_context(retry_after_apply=False)
    if ctx.blocked:
        pytest.skip(f"verify-api blocked: {ctx.blocked_reason}")
    return ctx.verify_api_base.rstrip("/")


def _live_api_reachable(api_base: str) -> bool:
    try:
        resp = httpx.get(f"{api_base}/api/v1/health", timeout=5.0)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def _post_json_loopback(
    api_base: str,
    path: str,
    *,
    expected_statuses: frozenset[int] = frozenset({200, 201, 204}),
) -> object:
    url = f"{api_base.rstrip('/')}{path}"
    if not url.startswith("http://127.0.0.1:"):
        raise ValueError(f"Live integration only permits loopback API URLs: {url}")
    resp = httpx.post(url, timeout=30.0)
    if resp.status_code not in expected_statuses:
        raise RuntimeError(f"HTTP POST {url} returned {resp.status_code}: {resp.text[:500]!r}")
    return resp.json() if resp.text else {}


def _assert_evicted_expired_404(payload: dict[str, object]) -> None:
    if payload.get("expired") is True:
        return
    detail = payload.get("detail")
    if isinstance(detail, dict) and detail.get("expired") is True:
        return
    raise AssertionError(f"Expected evicted expired 404 payload, got {payload!r}")


@pytest.mark.integration
class TestEvictedUecdLiveServerIntegration:
    """Hit running backend when ./myrm ready is up — critical path uses real disk + HTTP."""

    @pytest.mark.skipif(
        os.environ.get("MYRM_SKIP_LIVE_SERVER") == "1",
        reason="Live server checks disabled",
    )
    def test_live_evicted_api_reads_web_fetch_uecd_spill(self) -> None:
        api_base = _resolve_verify_api_base()
        if not _live_api_reachable(api_base):
            pytest.skip(f"Live API not reachable at {api_base}")

        seed = _post_json_loopback(
            api_base,
            "/api/v1/chats/test/seed-evicted-live-terminal-fixture",
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
        api_base = _resolve_verify_api_base()
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
        _assert_evicted_expired_404(payload)


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
