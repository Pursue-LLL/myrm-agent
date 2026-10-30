"""Contract: POST /cron/blueprints/fill reports every field a blueprint fill defines.

The web UI builds a blueprint job from this response alone, so a field the response leaves out is
silently lost from every job created there. The response must equal the fill, field for field.
"""

from __future__ import annotations

import json
from dataclasses import MISSING, asdict, fields, is_dataclass, replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.cron.routes import blueprints as blueprint_routes
from app.api.cron.routes.blueprints import router as blueprint_router
from app.core.cron.blueprints import (
    BUILTIN_BLUEPRINTS,
    BlueprintFailureAlertDefaults,
    BlueprintFillResult,
    BlueprintMonitorDefaults,
    BlueprintScheduleResult,
    CronBlueprint,
    fill_blueprint,
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(blueprint_router, prefix="/cron")
    return TestClient(app)


def _slot_values(blueprint: CronBlueprint) -> dict[str, str]:
    """Values for the slots a blueprint cannot default (the rest keep their defaults)."""
    return {slot.name: "sample" for slot in blueprint.slots if not slot.optional and not slot.default}


def _wire(fill: BlueprintFillResult) -> dict[str, object]:
    """The fill as the response reports it: tuples are lists, and no tool or skill list is an empty list."""
    wire: dict[str, object] = json.loads(json.dumps(asdict(fill)))
    wire["tools_allowed"] = wire["tools_allowed"] or []
    wire["skill_ids"] = wire["skill_ids"] or []
    return wire


_MONITOR = BlueprintMonitorDefaults(monitor_type="hash", ttl_days=7, enabled=False)
_ALERT = BlueprintFailureAlertDefaults(enabled=False, after=5, cooldown_seconds=60)
# Every field, nested ones included, differs from its default.
_FULL = BlueprintFillResult(
    schedule=BlueprintScheduleResult(kind="cron", expr="30 8 * * 1-5", tz="Asia/Shanghai", interval_ms=90_000),
    prompt="check the feed",
    name="Weekday digest",
    required_capabilities=("web_search",),
    tools_allowed=("read_file", "web_search"),
    skill_ids=("skill-a",),
    job_type="router",
    session_target="main",
    deduplicate=True,
    skip_if_active=True,
    timeout_seconds=123,
    monitor_config=_MONITOR,
    failure_alert=_ALERT,
    pre_condition_script="test -f /tmp/ready",
    command="echo done",
)
# A flag can differ from its default only one way, so each variant puts one flag back to tell crossed flags apart.
_FILLS = {
    "full": _FULL,
    "deduplicate-off": replace(_FULL, deduplicate=False),
    "skip-if-active-off": replace(_FULL, skip_if_active=False),
    "monitor-on": replace(_FULL, monitor_config=replace(_MONITOR, enabled=True)),
    "failure-alert-on": replace(_FULL, failure_alert=replace(_ALERT, enabled=True)),
}


def _assert_no_field_at_default(value: object) -> None:
    assert is_dataclass(value)
    for field in fields(value):
        current = getattr(value, field.name)
        if field.default is not MISSING:
            assert current != field.default, field.name
        if is_dataclass(current):
            _assert_no_field_at_default(current)


def test_full_fill_leaves_no_field_at_its_default() -> None:
    _assert_no_field_at_default(_FULL)


@pytest.mark.parametrize("fill", _FILLS.values(), ids=_FILLS.keys())
def test_response_reports_every_field_of_the_fill(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fill: BlueprintFillResult
) -> None:
    monkeypatch.setattr(blueprint_routes, "fill_blueprint", lambda *_args, **_kwargs: fill)

    response = client.post("/cron/blueprints/fill", json={"blueprint_id": "any"})

    assert response.status_code == 200, response.text
    assert response.json() == _wire(fill)


@pytest.mark.parametrize("blueprint", BUILTIN_BLUEPRINTS, ids=lambda bp: bp.id)
def test_response_reports_what_each_builtin_blueprint_fills(client: TestClient, blueprint: CronBlueprint) -> None:
    values = _slot_values(blueprint)
    fill = fill_blueprint(blueprint.id, values, locale="en")
    assert fill is not None

    response = client.post("/cron/blueprints/fill", json={"blueprint_id": blueprint.id, "values": values})

    assert response.status_code == 200, response.text
    assert response.json() == _wire(fill)
