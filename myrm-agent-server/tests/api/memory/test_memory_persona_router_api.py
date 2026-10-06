"""
[POS] tests/api/memory/test_memory_persona_router_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.persona_router, app.services.memory.memory_persona_router_service
[OUTPUT] test_route_persona_context_technical_execution_suppressed_api, test_route_persona_context_creative_communication_activated_api, test_route_persona_context_explicit_inline_directive_api, test_route_persona_context_empty_facets_safe_handling_api

Unit test suite for On-Demand Persona Skill and Anti-Pollution Context Router API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.persona_router import router as memory_persona_router
from app.services.memory.memory_persona_router_service import (
    MemoryPersonaRouterService,
    get_memory_persona_router_service,
)


@pytest.fixture
def persona_router_test_client() -> Generator[
    tuple[TestClient, MemoryPersonaRouterService], None, None
]:
    """Provide isolated TestClient mounting persona router with a clean service instance."""
    service = MemoryPersonaRouterService()

    test_app = FastAPI()
    test_app.include_router(memory_persona_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_persona_router_service] = (
        lambda: service
    )

    with TestClient(test_app) as client:
        yield client, service


def _sample_api_facets() -> list[dict[str, object]]:
    """Helper returning sample persona facet DTO dictionaries."""
    return [
        {
            "facet_id": "executive",
            "name": "商业高管汇报态",
            "tone_guidance": "金字塔原理，结论先行，ROI 导向",
            "sample_excerpts": ["季度增长超预期。"],
            "target_intents": ["creative_communication", "business"],
            "is_default": True,
            "estimated_tokens": 180,
        },
        {
            "facet_id": "engineer",
            "name": "技术极客极简态",
            "tone_guidance": "直出架构与代码，严禁客套",
            "sample_excerpts": ["零拷贝流式转发已就绪。"],
            "target_intents": ["technical_execution"],
            "is_default": False,
            "estimated_tokens": 120,
        },
    ]


def test_route_persona_context_technical_execution_suppressed_api(
    persona_router_test_client: tuple[TestClient, MemoryPersonaRouterService],
) -> None:
    """Verify technical execution queries strictly suppress persona injection."""
    client, _ = persona_router_test_client

    payload = {
        "query": "请帮我编写一个 Dockerfile 并排查容器端口映射报错",
        "facets": _sample_api_facets(),
    }
    res = client.post("/api/memory/persona/route-context", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["is_suppressed"] is True
    assert data["intent_category"] == "technical_execution"
    assert data["active_facets"] == []
    assert data["injected_content"] == ""
    assert data["tokens_saved_estimate"] == 300
    assert "suppressed" in data["decision_reason"].lower()


def test_route_persona_context_creative_communication_activated_api(
    persona_router_test_client: tuple[TestClient, MemoryPersonaRouterService],
) -> None:
    """Verify creative writing tasks activate matching persona facet."""
    client, _ = persona_router_test_client

    payload = {
        "query": "请帮我撰写一份关于季度架构升级成果的公关稿与对外汇报邮件",
        "facets": _sample_api_facets(),
    }
    res = client.post("/api/memory/persona/route-context", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["is_suppressed"] is False
    assert data["intent_category"] == "creative_communication"
    assert "executive" in data["active_facets"]
    assert "商业高管汇报态" in data["injected_content"]
    assert data["tokens_saved_estimate"] == 120


def test_route_persona_context_explicit_inline_directive_api(
    persona_router_test_client: tuple[TestClient, MemoryPersonaRouterService],
) -> None:
    """Verify explicit /about-me:engineer directive overrides suppression on code tasks."""
    client, _ = persona_router_test_client

    payload = {
        "query": "请用 python 重写这个解析器，并遵循 /about-me:engineer 风格",
        "facets": _sample_api_facets(),
    }
    res = client.post("/api/memory/persona/route-context", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["is_suppressed"] is False
    assert "engineer" in data["active_facets"]
    assert "技术极客极简态" in data["injected_content"]
    assert data["tokens_saved_estimate"] == 180


def test_route_persona_context_empty_facets_safe_handling_api(
    persona_router_test_client: tuple[TestClient, MemoryPersonaRouterService],
) -> None:
    """Verify empty candidate facets list is safely handled."""
    client, _ = persona_router_test_client

    payload = {
        "query": "撰写一封周报",
        "facets": [],
    }
    res = client.post("/api/memory/persona/route-context", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["is_suppressed"] is True
    assert data["active_facets"] == []
    assert data["injected_content"] == ""
