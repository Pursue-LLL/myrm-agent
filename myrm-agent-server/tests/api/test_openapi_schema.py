"""Verify OpenAPI security metadata without importing app.main."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.server.openapi_security import OPENAPI_API_DESCRIPTION, enrich_openapi_schema, install_custom_openapi
from tests.support.minimal_app import build_minimal_app


@pytest.fixture()
def openapi_schema() -> dict:
    app = build_minimal_app(preset="health", include_health_check=True)
    app.description = OPENAPI_API_DESCRIPTION
    install_custom_openapi(app)
    app.openapi_schema = None
    return app.openapi()


def test_security_scheme_present(openapi_schema: dict) -> None:
    schemes = openapi_schema.get("components", {}).get("securitySchemes", {})
    assert "bearerAuth" in schemes
    bearer = schemes["bearerAuth"]
    assert bearer["type"] == "http"
    assert bearer["scheme"] == "bearer"


def test_global_security_requirement(openapi_schema: dict) -> None:
    security = openapi_schema.get("security", [])
    assert any("bearerAuth" in item for item in security)


def test_description_not_empty(openapi_schema: dict) -> None:
    info = openapi_schema.get("info", {})
    desc = info.get("description", "")
    assert len(desc) > 50
    assert "Authentication" in desc


def test_schema_is_cached() -> None:
    app = FastAPI(title="Cache Test")
    install_custom_openapi(app)
    app.openapi_schema = None
    first = app.openapi()
    second = app.openapi()
    assert first is second


def test_enrich_openapi_schema_standalone() -> None:
    schema: dict[str, object] = {"components": {}}
    enriched = enrich_openapi_schema(schema)
    schemes = enriched.get("components", {})
    assert isinstance(schemes, dict)
    security_schemes = schemes.get("securitySchemes", {})
    assert isinstance(security_schemes, dict)
    assert "bearerAuth" in security_schemes
