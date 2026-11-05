"""[INPUT]
- pydantic::BaseModel (POS: schema base)

[OUTPUT]
- DLQMetrics, HealthMetricsResponse

[POS]
Control-plane schemas: dead-letter metrics and the health response.
"""

from __future__ import annotations

from pydantic import BaseModel


class DLQMetrics(BaseModel):
    """Dead Letter Queue metrics."""

    failed_count: int
    status: str
    error: str | None = None


class HealthMetricsResponse(BaseModel):
    """System metrics exposed to the control plane."""

    dlq: DLQMetrics
