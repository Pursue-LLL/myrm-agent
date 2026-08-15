"""Integration test: harness metrics reach the server Prometheus /metrics endpoint.

Real cross-layer link for the metrics fix:
1. Harness ``MetricsRegistry`` registers its counters on the global Prometheus
   ``REGISTRY`` (same registry that ``app.core.monitoring._setup_metrics``
   exposes at ``GET /metrics``).
2. Recording an approval denial / hook failure through the real harness
   registry makes the new counters appear in the server's scrape output.
"""

from __future__ import annotations

import pytest

pytest.importorskip("prometheus_client")

from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def metrics_app() -> FastAPI:
    """Minimal app exposing /metrics exactly like the production endpoint body.

    The production ``_setup_metrics`` serves ``Response(content=generate_latest())``;
    we replicate that endpoint so the test does not depend on optional extras
    (e.g. ``prometheus-fastapi-instrumentator``) being installed in the local venv.
    """
    from fastapi import Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    app = FastAPI()

    @app.get("/metrics", include_in_schema=False)
    def metrics_endpoint() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


@pytest.mark.integration
def test_server_metrics_endpoint_exposes_harness_approval_counter(
    metrics_app: FastAPI,
) -> None:
    from myrm_agent_harness.observability.metrics.registry import metrics_registry

    assert metrics_registry.enabled
    metrics_registry.record_approval_denied(
        agent_id="it-server", tool_name="bash_code_execute_tool", reason="subagent_auto_deny"
    )

    client = TestClient(metrics_app)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    text = response.text

    assert "agent_approval_denied_total" in text
    assert 'agent_id="it-server"' in text
    assert 'reason="subagent_auto_deny"' in text


@pytest.mark.integration
def test_server_metrics_endpoint_exposes_harness_hook_counter(
    metrics_app: FastAPI,
) -> None:
    from myrm_agent_harness.observability.metrics.registry import metrics_registry

    assert metrics_registry.enabled
    metrics_registry.record_hook_failure(
        agent_id="it-server", tool_name="bash_code_execute_tool", hook_event="post_tool_use"
    )

    client = TestClient(metrics_app)
    response = client.get("/metrics")
    assert response.status_code == 200
    text = response.text

    assert "agent_hook_failures_total" in text
    assert 'agent_id="it-server"' in text
    assert 'hook_event="post_tool_use"' in text
