"""Server-level Proxy Alignment Guard for Skill Growth evaluation and adoption.

[INPUT]
- myrm_agent_harness.eval.metric_contract::(evaluate_metric_proxy_alignment, MetricContract)

[OUTPUT]
- evaluate_case_proxy_alignment: Evaluate candidate growth case for Goodhart's Law drift

[POS]
Business service guarding Skill Growth adoption against proxy metric manipulation.
"""

from __future__ import annotations

import logging
from typing import Any

from myrm_agent_harness.eval.metric_contract import (
    MetricContract,
    evaluate_metric_proxy_alignment,
)

logger = logging.getLogger(__name__)


def evaluate_case_proxy_alignment(payload: dict[str, Any]) -> dict[str, object] | None:
    """Evaluate proxy alignment for a skill growth candidate case from its prediction manifest.

    Extracts baseline vs candidate metric projections and determines whether efficiency gains
    align with core intent or exhibit Goodhart's Law corner-cutting drift.
    """
    manifest_data = payload.get("prediction_manifest")
    if not isinstance(manifest_data, dict):
        return None

    predictions = manifest_data.get("predictions")
    if not isinstance(predictions, list) or not predictions:
        return None

    baseline_metrics: dict[str, float] = {}
    candidate_metrics: dict[str, float] = {}

    for pred in predictions:
        if not isinstance(pred, dict):
            continue
        metric_name = pred.get("metric_name")
        if not isinstance(metric_name, str) or not metric_name:
            continue
        try:
            b_val = float(pred.get("baseline_value", 0.0))
            c_val = float(pred.get("predicted_value", 0.0))
            baseline_metrics[metric_name] = b_val
            candidate_metrics[metric_name] = c_val
        except (ValueError, TypeError):
            continue

    if not baseline_metrics or not candidate_metrics:
        return None

    sample_size = int(manifest_data.get("sample_size", 10))

    try:
        analysis = evaluate_metric_proxy_alignment(
            baseline_metrics=baseline_metrics,
            candidate_metrics=candidate_metrics,
            contract=None,  # Uses default canonical MetricContract
            sample_size=sample_size,
        )
        return analysis.to_dict()
    except Exception as e:
        logger.warning("Failed to evaluate proxy alignment for growth case: %s", e)
        return None
