"""Optional router loading must degrade per feature, never break the API import."""

from __future__ import annotations

from fastapi import APIRouter

from app.api._optional_routers import OptionalRouterSpec, register_optional_routers


def test_missing_optional_module_is_skipped() -> None:
    api_router = APIRouter()
    report = register_optional_routers(
        api_router,
        (OptionalRouterSpec("absent", "app.api.agents.__definitely_missing__"),),
    )
    assert report.registered == ()
    assert report.skipped and report.skipped[0][0] == "absent"


def test_present_optional_module_is_registered() -> None:
    api_router = APIRouter()
    report = register_optional_routers(
        api_router,
        (OptionalRouterSpec("fleet", "app.api.agents.fleet_overview", "/agents", ("agents",)),),
    )
    assert "fleet" in report.registered
    assert report.skipped == ()
    assert api_router.routes
