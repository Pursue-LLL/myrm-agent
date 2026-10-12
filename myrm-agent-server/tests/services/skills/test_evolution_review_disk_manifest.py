"""Change-manifest attribution after an evolution is applied."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.skills.evolution_review.disk import _attribute_manifest_after_apply
from app.services.skills.evolution_review.types import EvolutionApprovalPayload


def _payload(change_manifest: dict[str, object] | None) -> EvolutionApprovalPayload:
    return EvolutionApprovalPayload(
        skill_id="skill-1",
        skill_name="uv-usage",
        skill_path="/skills/uv-usage",
        evolution_type="fix",
        reason="user correction",
        original_content="use pip",
        evolved_content="prefer uv over pip",
        confidence=0.9,
        test_passed=True,
        change_manifest=change_manifest,
    )


def _manifest(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "manifest_id": "m-1",
        "target_component": "skills/uv-usage",
        "rationale": "tighten the install guidance",
        "predictions": [
            {
                "metric_name": "pass_rate",
                "direction": "increase",
                "baseline_value": 0.5,
                "target_value": 0.8,
                "tolerance": 0.05,
            }
        ],
    }
    return {**base, **overrides}


@pytest.mark.parametrize(
    "change_manifest",
    [None, {}, {"predictions": []}, {"predictions": "pass_rate"}, {"predictions": {"metric_name": "pass_rate"}}],
    ids=["no-manifest", "empty-manifest", "empty-predictions", "string-predictions", "mapping-predictions"],
)
def test_manifest_without_a_list_of_predictions_is_not_attributed(change_manifest: dict[str, object] | None) -> None:
    assert _attribute_manifest_after_apply(_payload(change_manifest)) is None


@pytest.mark.parametrize("timestamp", [None, 1_700_000_000, "2026-10-13T00:00:00Z"], ids=["none", "number", "text"])
def test_a_well_formed_manifest_is_attributed_whatever_the_optional_fields_hold(timestamp: object) -> None:
    manifest = _manifest(created_at=timestamp, rollback_patch=timestamp)
    with patch(
        "myrm_agent_harness.agent.skills.evolution.core.eval_regression.evaluate_content_assertions",
        return_value=0.9,
    ):
        result = _attribute_manifest_after_apply(_payload(manifest))

    assert result is not None
    assert result["manifest_id"] == "m-1"


def test_a_malformed_prediction_value_degrades_to_no_attribution() -> None:
    manifest = _manifest(predictions=[{"metric_name": "pass_rate", "baseline_value": "not-a-number"}])
    with patch(
        "myrm_agent_harness.agent.skills.evolution.core.eval_regression.evaluate_content_assertions",
        return_value=0.9,
    ):
        assert _attribute_manifest_after_apply(_payload(manifest)) is None
