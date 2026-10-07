# [POS]: tests/api/memory/test_rule_cascade_api.py
# [INPUT]: app.api.memory.rule_cascade_router, isolated FastAPI app
# [OUTPUT]: Integration API tests for FiveDimPreFilteredEvidenceMemoryAndDeterministicRuleCascadeSuite (Item 99)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.rule_cascade_router import router as rule_cascade_router
from app.services.memory.rule_cascade_service import (
    RuleCascadeService,
    get_rule_cascade_service,
)


@pytest.fixture
def isolated_service() -> RuleCascadeService:
    """Provides an isolated in-memory RuleCascadeService instance."""
    return RuleCascadeService()


@pytest.fixture
def test_app(isolated_service: RuleCascadeService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(rule_cascade_router, prefix="/api/memory")
    app.dependency_overrides[get_rule_cascade_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_rule_registration_and_hierarchical_cascade_api(test_app: FastAPI) -> None:
    """Validate registering rules and resolving deterministic hierarchical cascade via REST APIs."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register root rule
        r1_payload = {
            "rule_id": "rule-root-pep8",
            "title": "Code Formatting",
            "rule_content": "Standard PEP-8 line length 100",
            "metadata": {
                "scope": "global",
                "scope_path": "/",
                "source": "agent_inferred",
                "source_authority": 0.4,
                "permission": "public",
            },
        }
        res1 = await client.post("/api/memory/rules/register", json=r1_payload)
        assert res1.status_code == 200
        assert res1.json()["is_success"] is True

        # 2. Register workspace rule
        r2_payload = {
            "rule_id": "rule-ws-test",
            "title": "Testing Standard",
            "rule_content": "Mandatory pytest with 90% coverage",
            "metadata": {
                "scope": "workspace",
                "scope_path": "/workspace",
                "source": "tool_verified",
                "source_authority": 0.8,
                "permission": "workspace_internal",
            },
        }
        res2 = await client.post("/api/memory/rules/register", json=r2_payload)
        assert res2.status_code == 200

        # 3. Register billing leaf rule (overrides Code Formatting with stricter rules)
        r3_payload = {
            "rule_id": "rule-billing-strict",
            "title": "Code Formatting",
            "rule_content": "Strict zero-warning Ruff checks required",
            "metadata": {
                "scope": "directory",
                "scope_path": "/workspace/packages/billing",
                "source": "user_explicit",
                "source_authority": 1.0,
                "permission": "workspace_internal",
            },
        }
        res3 = await client.post("/api/memory/rules/register", json=r3_payload)
        assert res3.status_code == 200

        # 4. Resolve cascade for nested path inside billing
        cascade_req = {
            "target_path": "/workspace/packages/billing/controllers",
        }
        casc_res = await client.post("/api/memory/rules/cascade", json=cascade_req)
        assert casc_res.status_code == 200
        casc_data = casc_res.json()

        assert casc_data["target_path"] == "/workspace/packages/billing/controllers"
        assert casc_data["effective_rules_count"] == 2

        by_title = {r["title"]: r for r in casc_data["inherited_rules"]}
        assert "Testing Standard" in by_title
        assert "Code Formatting" in by_title
        # Leaf rule won
        assert by_title["Code Formatting"]["rule_id"] == "rule-billing-strict"
        assert "Strict zero-warning Ruff" in by_title["Code Formatting"]["rule_content"]

        # 5. List all rules
        list_res = await client.get("/api/memory/rules/list")
        assert list_res.status_code == 200
        all_rules = list_res.json()
        assert len(all_rules) == 3


@pytest.mark.asyncio
async def test_five_dim_pre_filtering_api(test_app: FastAPI) -> None:
    """Validate 5-dimensional pre-filtering API blocking unauthorized/out-of-scope candidates."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        candidates_payload = [
            # Valid item
            {
                "rule_id": "valid-01",
                "title": "Auth Rule",
                "rule_content": "Use OAuth2 bearer tokens",
                "metadata": {
                    "scope": "workspace",
                    "scope_path": "/workspace/auth",
                    "source": "user_explicit",
                    "source_authority": 1.0,
                    "confidence": 1.0,
                    "permission": "workspace_internal",
                },
            },
            # Blocked item: confidential admin
            {
                "rule_id": "blocked-conf",
                "title": "DB Master Password",
                "rule_content": "Root credentials",
                "metadata": {
                    "scope": "workspace",
                    "scope_path": "/workspace/auth",
                    "source": "user_explicit",
                    "source_authority": 1.0,
                    "confidence": 1.0,
                    "permission": "confidential_admin",
                },
            },
            # Blocked item: low authority
            {
                "rule_id": "blocked-low-auth",
                "title": "Heuristic Guess",
                "rule_content": "Maybe timeout is 30s",
                "metadata": {
                    "scope": "workspace",
                    "scope_path": "/workspace/auth",
                    "source": "agent_inferred",
                    "source_authority": 0.4,
                    "confidence": 1.0,
                    "permission": "public",
                },
            },
        ]

        filter_req = {
            "candidates": candidates_payload,
            "scope_path_prefix": "/workspace",
            "min_authority": 0.8,
            "min_confidence": 0.5,
            "required_permission": "workspace_internal",
        }

        res = await client.post("/api/memory/rules/pre-filter", json=filter_req)
        assert res.status_code == 200
        data = res.json()

        assert data["total_evaluated"] == 3
        assert data["passed_count"] == 1
        assert data["passed_items"][0]["rule_id"] == "valid-01"
        assert data["rejection_reasons"]["permission_denied"] == 1
        assert data["rejection_reasons"]["authority_insufficient"] == 1
