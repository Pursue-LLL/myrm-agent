"""Architecture test: every field the cron REST schemas declare is read by its route and returned by the response mapper.

A request field the route never reads is accepted, validated and then dropped, so the setting looks saved
and does nothing; a response field the mapper never sets always reads as its default.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable

import pytest

from app.api.cron.routes import helpers, jobs
from app.api.cron.schemas import CronJobCreate, CronJobResponse, CronJobUpdate

pytestmark = pytest.mark.architecture

# Declared on the create schema but advisory: the create dialog shows the prerequisite card and the server never acts on it.
# An entry that the route starts reading must be removed, so a stale entry fails the create test.
_ACCEPTED_BUT_IGNORED = {"override_prerequisite"}


def request_fields_read(source: str) -> set[str]:
    """Names read as ``body.<field>`` in a route function's source."""
    return {
        node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "body"
    }


def response_fields_set(source: str) -> set[str]:
    """Keyword names passed to ``CronJobResponse(...)`` in the mapper's source."""
    return {
        keyword.arg
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "CronJobResponse"
        for keyword in node.keywords
        if keyword.arg
    }


def _source(func: Callable[..., object]) -> str:
    return textwrap.dedent(inspect.getsource(func))


def test_create_route_reads_every_request_field() -> None:
    unread = set(CronJobCreate.model_fields) - request_fields_read(_source(jobs.create_job))

    assert unread == _ACCEPTED_BUT_IGNORED, sorted(unread)


def test_update_route_reads_every_request_field() -> None:
    unread = set(CronJobUpdate.model_fields) - request_fields_read(_source(jobs.update_job))

    assert not unread, sorted(unread)


def test_response_mapper_sets_every_response_field() -> None:
    unset = set(CronJobResponse.model_fields) - response_fields_set(_source(helpers._to_response))

    assert not unset, sorted(unset)


def test_detectors_report_a_field_the_code_stops_using() -> None:
    """Calibration: the readers see a forwarded field, and miss it once the line carrying it is gone."""
    route = _source(jobs.create_job)
    route_without = route.replace("skip_if_active=body.skip_if_active,", "")
    assert route != route_without
    assert "skip_if_active" in request_fields_read(route)
    assert "skip_if_active" not in request_fields_read(route_without)

    mapper = _source(helpers._to_response)
    mapper_without = mapper.replace("skip_if_active=job.skip_if_active,", "")
    assert mapper != mapper_without
    assert "skip_if_active" in response_fields_set(mapper)
    assert "skip_if_active" not in response_fields_set(mapper_without)
