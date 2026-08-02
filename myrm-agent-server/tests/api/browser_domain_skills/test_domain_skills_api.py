"""Integration tests for browser domain skills CRUD API.

Tests the full HTTP request chain: list → get → distill → verify → delete.
Uses ASGI TestClient (no network, no mock on critical path).
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app

API_PREFIX = "/api/v1"


@pytest.fixture
def domain_skills_app():
    return build_minimal_app(preset="browser_domain_skills")


# ---------------------------------------------------------------------------
# GET /browser/domain-skills — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_domain_skills_returns_builtin(domain_skills_app) -> None:
    """Builtin x-com skill should appear in the list with is_builtin=True."""
    async with AsyncClient(
        transport=ASGITransport(app=domain_skills_app),
        base_url="http://test",
    ) as ac:
        resp = await ac.get(f"{API_PREFIX}/browser/domain-skills")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        ids = {s["id"] for s in data}
        assert "x-com" in ids
        x_com = next(s for s in data if s["id"] == "x-com")
        assert x_com["is_builtin"] is True
        assert "x.com" in x_com["domains"] or "twitter.com" in x_com["domains"]
        assert isinstance(x_com["python_tools"], dict)


# ---------------------------------------------------------------------------
# GET /browser/domain-skills/{skill_id} — get single
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_domain_skill_existing(domain_skills_app) -> None:
    """Getting x-com by ID should return full detail."""
    async with AsyncClient(
        transport=ASGITransport(app=domain_skills_app),
        base_url="http://test",
    ) as ac:
        resp = await ac.get(f"{API_PREFIX}/browser/domain-skills/x-com")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "x-com"
        assert data["name"] == "X (Twitter)"
        assert data["is_builtin"] is True


@pytest.mark.asyncio
async def test_get_domain_skill_not_found(domain_skills_app) -> None:
    """Getting a nonexistent skill should return 404."""
    async with AsyncClient(
        transport=ASGITransport(app=domain_skills_app),
        base_url="http://test",
    ) as ac:
        resp = await ac.get(f"{API_PREFIX}/browser/domain-skills/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /browser/domain-skills/distill — create via distillation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_distill_and_verify(domain_skills_app, tmp_path, monkeypatch) -> None:
    """Distill a new skill, verify it appears in list, then clean up."""
    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path))

    import myrm_agent_harness.toolkits.browser.domain_skills.store as store_mod
    store_mod._global_store = None

    try:
        async with AsyncClient(
            transport=ASGITransport(app=domain_skills_app),
            base_url="http://test",
        ) as ac:
            payload = {
                "skill_id": "test-distill",
                "name": "Test Distill Skill",
                "domains": ["test-distill.example.com"],
                "tools": {
                    "fetch_data": {
                        "description": "Fetch data from page",
                        "script_content": "async def fetch_data(session, args):\n    return 'ok'\n",
                        "callable_name": "fetch_data",
                        "args": {"url": {"type": "string", "required": "true"}},
                        "returns": "fetched data",
                    },
                },
            }
            resp = await ac.post(
                f"{API_PREFIX}/browser/domain-skills/distill",
                json=payload,
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            assert data["id"] == "test-distill"
            assert data["name"] == "Test Distill Skill"
            assert "fetch_data" in data["python_tools"]

            resp = await ac.get(f"{API_PREFIX}/browser/domain-skills/test-distill")
            assert resp.status_code == 200
            detail = resp.json()
            assert detail["id"] == "test-distill"
            assert detail["is_builtin"] is False

            resp = await ac.delete(f"{API_PREFIX}/browser/domain-skills/test-distill")
            assert resp.status_code == 200
            assert resp.json()["deleted"] is True

            resp = await ac.get(f"{API_PREFIX}/browser/domain-skills/test-distill")
            assert resp.status_code == 404
    finally:
        store_mod._global_store = None


@pytest.mark.asyncio
async def test_distill_duplicate_rejected(domain_skills_app, tmp_path, monkeypatch) -> None:
    """Distilling a skill with existing ID should return 409."""
    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path))

    import myrm_agent_harness.toolkits.browser.domain_skills.store as store_mod
    store_mod._global_store = None

    try:
        async with AsyncClient(
            transport=ASGITransport(app=domain_skills_app),
            base_url="http://test",
        ) as ac:
            payload = {
                "skill_id": "dup-test",
                "name": "Dup",
                "domains": ["dup.com"],
                "tools": {},
            }
            resp = await ac.post(
                f"{API_PREFIX}/browser/domain-skills/distill",
                json=payload,
            )
            assert resp.status_code == 201

            resp = await ac.post(
                f"{API_PREFIX}/browser/domain-skills/distill",
                json=payload,
            )
            assert resp.status_code == 409
    finally:
        store_mod._global_store = None


@pytest.mark.asyncio
async def test_distill_path_traversal_rejected(domain_skills_app) -> None:
    """Tool names with path traversal should be rejected at validation."""
    async with AsyncClient(
        transport=ASGITransport(app=domain_skills_app),
        base_url="http://test",
    ) as ac:
        payload = {
            "skill_id": "evil-skill",
            "name": "Evil",
            "domains": ["evil.com"],
            "tools": {
                "../../backdoor": {
                    "description": "x",
                    "script_content": "x",
                    "callable_name": "x",
                },
            },
        }
        resp = await ac.post(
            f"{API_PREFIX}/browser/domain-skills/distill",
            json=payload,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /browser/domain-skills/{skill_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_404(domain_skills_app) -> None:
    """Deleting a nonexistent skill should return 404."""
    async with AsyncClient(
        transport=ASGITransport(app=domain_skills_app),
        base_url="http://test",
    ) as ac:
        resp = await ac.delete(f"{API_PREFIX}/browser/domain-skills/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Edge: distill writes files to disk, skill is matchable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_distill_writes_script_to_disk(domain_skills_app, tmp_path, monkeypatch) -> None:
    """Distilled skill script should be persisted to disk with correct content."""
    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path))

    import myrm_agent_harness.toolkits.browser.domain_skills.store as store_mod
    store_mod._global_store = None

    script_body = "async def greet(session, args):\n    return 'hello'\n"
    try:
        async with AsyncClient(
            transport=ASGITransport(app=domain_skills_app),
            base_url="http://test",
        ) as ac:
            payload = {
                "skill_id": "disk-test",
                "name": "Disk Test",
                "domains": ["disk-test.example.com"],
                "tools": {
                    "greet": {
                        "description": "Greet",
                        "script_content": script_body,
                        "callable_name": "greet",
                    },
                },
            }
            resp = await ac.post(
                f"{API_PREFIX}/browser/domain-skills/distill",
                json=payload,
            )
            assert resp.status_code == 201

        script_path = tmp_path / "domain_skills" / "disk-test" / "tools" / "greet.py"
        assert script_path.exists()
        assert script_path.read_text(encoding="utf-8") == script_body

        manifest_path = tmp_path / "domain_skills" / "disk-test" / "manifest.json"
        assert manifest_path.exists()
    finally:
        store_mod._global_store = None


@pytest.mark.asyncio
async def test_distill_skill_id_max_length(domain_skills_app) -> None:
    """skill_id exceeding 64 chars should be rejected."""
    async with AsyncClient(
        transport=ASGITransport(app=domain_skills_app),
        base_url="http://test",
    ) as ac:
        payload = {
            "skill_id": "a" * 65,
            "name": "Too Long",
            "domains": ["long.com"],
            "tools": {},
        }
        resp = await ac.post(
            f"{API_PREFIX}/browser/domain-skills/distill",
            json=payload,
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_reflects_distilled_skill(domain_skills_app, tmp_path, monkeypatch) -> None:
    """Newly distilled skill should appear in list with correct is_builtin=False."""
    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path))

    import myrm_agent_harness.toolkits.browser.domain_skills.store as store_mod
    store_mod._global_store = None

    try:
        async with AsyncClient(
            transport=ASGITransport(app=domain_skills_app),
            base_url="http://test",
        ) as ac:
            payload = {
                "skill_id": "list-test",
                "name": "List Test",
                "domains": ["list-test.com"],
                "tools": {},
            }
            resp = await ac.post(
                f"{API_PREFIX}/browser/domain-skills/distill",
                json=payload,
            )
            assert resp.status_code == 201

            resp = await ac.get(f"{API_PREFIX}/browser/domain-skills")
            data = resp.json()
            ids = {s["id"] for s in data}
            assert "list-test" in ids
            lt = next(s for s in data if s["id"] == "list-test")
            assert lt["is_builtin"] is False
    finally:
        store_mod._global_store = None
