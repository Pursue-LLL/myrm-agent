"""FastAPI Prometheus Instrumentator setup.

Provides HTTP request monitoring with noise exclusion.
"""

from __future__ import annotations

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def setup_http_metrics(app: FastAPI) -> Instrumentator:
    """Setup FastAPI Prometheus Instrumentator.

    Provides automatic HTTP request monitoring:
    - Request count by method/endpoint/status_code
    - Request duration (histogram)
    - In-progress requests (gauge)

    Excludes noisy endpoints:
    - /health (K8s health checks)
    - /metrics (Prometheus scrapes)
    - /openapi.json (API spec fetches)

    Args:
        app: FastAPI application instance

    Returns:
        Instrumentator instance
    """
    instrumentator = Instrumentator(
        should_group_status_codes=False,  # Report exact status codes (401, 403, 500, etc.)
        should_instrument_requests_inprogress=True,  # Enable in-progress request gauge
        inprogress_labels=True,  # Break down by method and handler
        excluded_handlers=["/health", "/metrics", "/openapi.json"],  # Exclude noise
        inprogress_name="myrm_http_requests_inprogress",  # Add myrm_ prefix
        should_respect_env_var=False,  # Always enable
    )

    # Instrument app
    instrumentator.instrument(app)

    return instrumentator
