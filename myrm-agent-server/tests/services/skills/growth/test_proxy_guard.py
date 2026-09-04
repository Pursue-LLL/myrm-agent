"""Unit tests for Server-level Proxy Alignment Guard."""

from __future__ import annotations

from app.services.skills.growth.proxy_guard import evaluate_case_proxy_alignment


def test_evaluate_case_proxy_alignment_missing_manifest() -> None:
    """Verify missing or invalid prediction manifest safely returns None."""
    assert evaluate_case_proxy_alignment({}) is None
    assert evaluate_case_proxy_alignment({"prediction_manifest": "invalid"}) is None
    assert evaluate_case_proxy_alignment({"prediction_manifest": {"predictions": []}}) is None


def test_evaluate_case_proxy_alignment_aligned() -> None:
    """Verify aligned candidate variant produces aligned verdict."""
    payload = {
        "prediction_manifest": {
            "sample_size": 10,
            "predictions": [
                {
                    "metric_name": "pass_rate",
                    "baseline_value": 0.8,
                    "predicted_value": 0.95,
                },
                {
                    "metric_name": "tokens",
                    "baseline_value": 2000.0,
                    "predicted_value": 1500.0,
                },
            ],
        }
    }

    result = evaluate_case_proxy_alignment(payload)
    assert result is not None
    assert result["verdict"] == "aligned"
    assert result["intent_delta"] > 0
    assert result["proxy_improvement"] > 0


def test_evaluate_case_proxy_alignment_goodhart_drift() -> None:
    """Verify corner-cutting variant triggering Goodhart's law is caught."""
    payload = {
        "prediction_manifest": {
            "sample_size": 10,
            "predictions": [
                {
                    "metric_name": "pass_rate",
                    "baseline_value": 0.9,
                    "predicted_value": 0.6,
                },
                {
                    "metric_name": "tokens",
                    "baseline_value": 5000.0,
                    "predicted_value": 2000.0,
                },
                {
                    "metric_name": "tool_calls",
                    "baseline_value": 10.0,
                    "predicted_value": 3.0,
                },
            ],
        }
    }

    result = evaluate_case_proxy_alignment(payload)
    assert result is not None
    assert result["verdict"] == "goodhart_drift"
    assert "Goodhart's Law Drift detected" in str(result["warning_message"])


def test_evaluate_case_proxy_alignment_malformed_values() -> None:
    """Verify malformed non-numeric values do not crash evaluation."""
    payload = {
        "prediction_manifest": {
            "predictions": [
                {
                    "metric_name": "pass_rate",
                    "baseline_value": "not-a-number",
                    "predicted_value": 0.9,
                }
            ]
        }
    }
    assert evaluate_case_proxy_alignment(payload) is None
