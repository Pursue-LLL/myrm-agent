"""Tests for model switch preflight endpoint.

Covers:
- POST /api/v1/integrations/llm/model-switch-preflight response schema
- Threshold computation matches harness ContextConfig formula
- compress_start_ratio tier inference (WEAK/MEDIUM/STRONG)
- Frontend-provided window fallback for unknown models
- Request validation (422 on invalid input)
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed via loopback IP mock."""
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class TestModelSwitchPreflight:
    """Preflight endpoint tests."""

    def test_empty_models_list(self, client: TestClient) -> None:
        """Empty models list should return empty results."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={"estimated_tokens": 10000, "models": []},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["results"] == []

    def test_missing_required_fields(self, client: TestClient) -> None:
        """Missing estimated_tokens should return 422."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={"models": [{"model": "gpt-4o"}]},
        )
        assert response.status_code == 422

    def test_negative_turn_count_rejected(self, client: TestClient) -> None:
        """Negative turn_count violates the ge=0 contract and must be rejected."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 1000,
                "turn_count": -1,
                "models": [{"model": "gpt-4o"}],
            },
        )
        assert response.status_code == 422

    def test_unknown_model_with_frontend_window(self, client: TestClient) -> None:
        """Frontend-provided window drives threshold even when litellm is unknown.

        Window 16k maps to WEAK tier (context-length based) -> ratio 0.30.
        """
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 9000,
                "models": [
                    {"model": "custom/mystery-model", "max_input_tokens": 16000}
                ],
            },
        )
        assert response.status_code == 200
        results = response.json()["data"]["results"]
        assert len(results) == 1
        item = results[0]
        assert item["model"] == "custom/mystery-model"
        assert item["found"] is True
        assert item["new_window"] == 16000
        # WEAK tier -> gap = (0.95 - 0.30) / 3 = 0.2167; threshold = 16000 * 0.5167 = 8266
        assert item["compress_threshold"] == int(16000 * (0.30 + (0.95 - 0.30) / 3.0))
        assert item["will_compress"] is True

    def test_small_window_does_not_compress(self, client: TestClient) -> None:
        """Small estimated tokens below threshold should not compress."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 1000,
                "models": [
                    {"model": "custom/mystery-model", "max_input_tokens": 16000}
                ],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        assert item["will_compress"] is False

    def test_explicit_compress_start_ratio(self, client: TestClient) -> None:
        """Explicit ratio overrides tier inference and follows ContextConfig formula."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 24000,
                "compress_start_ratio": 0.6,
                "models": [
                    {"model": "custom/mystery-model", "max_input_tokens": 32000}
                ],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        # gap = (0.95 - 0.6) / 3 = 0.1167; threshold = 32000 * (0.6 + 0.1167) = 22933
        assert item["compress_threshold"] == int(32000 * (0.6 + (0.95 - 0.6) / 3.0))
        assert item["will_compress"] is True

    def test_weak_tier_inference(self, client: TestClient) -> None:
        """Small window (<=16k) maps to WEAK tier -> ratio 0.30 -> threshold ≈ 0.5167*window."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 8000,
                "models": [{"model": "custom/small-local", "max_input_tokens": 8192}],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        # gap = (0.95 - 0.30) / 3 = 0.2167; threshold = 8192 * 0.5167 = 4232
        expected = int(8192 * (0.30 + (0.95 - 0.30) / 3.0))
        assert item["compress_threshold"] == expected
        assert item["will_compress"] is True

    def test_medium_tier_inference(self, client: TestClient) -> None:
        """Medium window (16k < window <= 64k) maps to MEDIUM tier -> ratio 0.50."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 30000,
                "models": [{"model": "custom/medium-model", "max_input_tokens": 32000}],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        # gap = (0.95 - 0.50) / 3 = 0.15; threshold = 32000 * 0.65 = 20800
        expected = int(32000 * (0.50 + (0.95 - 0.50) / 3.0))
        assert item["compress_threshold"] == expected
        assert item["will_compress"] is True

    def test_strong_tier_default_threshold(self, client: TestClient) -> None:
        """Large window (>64k) maps to STRONG tier -> default ratio None -> 0.5*window."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 150000,
                "models": [{"model": "custom/big-model", "max_input_tokens": 200000}],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        assert item["compress_threshold"] == 100000
        assert item["will_compress"] is True

    def test_multiple_models(self, client: TestClient) -> None:
        """Multiple models return independent results."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 12000,
                "models": [
                    {"model": "custom/a", "max_input_tokens": 16000},
                    {"model": "custom/b", "max_input_tokens": 100000},
                ],
            },
        )
        assert response.status_code == 200
        results = response.json()["data"]["results"]
        assert len(results) == 2
        by_model = {item["model"]: item for item in results}
        # 16000 -> WEAK threshold ~8266 -> will compress
        assert by_model["custom/a"]["will_compress"] is True
        # 100000 -> STRONG threshold 50000 -> no compress
        assert by_model["custom/b"]["will_compress"] is False

    def test_out_of_range_compress_start_ratio_is_clamped(
        self, client: TestClient
    ) -> None:
        """Out-of-range ratio is clamped by harness ContextConfig instead of rejected.

        Mirrors runtime behavior: ContextConfig._effective_ratio clamps to [0.20, 0.85].
        """
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 10000,
                "compress_start_ratio": 1.5,
                "models": [
                    {"model": "custom/mystery-model", "max_input_tokens": 16000}
                ],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        # clamped to 0.85 -> gap = (0.95 - 0.85) / 3 = 0.0333; threshold = 16000 * 0.8833
        expected = int(16000 * (0.85 + (0.95 - 0.85) / 3.0))
        assert item["compress_threshold"] == expected

    def test_low_compress_start_ratio_is_clamped(self, client: TestClient) -> None:
        """Low out-of-range ratio clamps up to 0.20."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 10000,
                "compress_start_ratio": 0.1,
                "models": [
                    {"model": "custom/mystery-model", "max_input_tokens": 16000}
                ],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        expected = int(16000 * (0.20 + (0.95 - 0.20) / 3.0))
        assert item["compress_threshold"] == expected

    def test_prompt_mode_lean_skips_tier_inference(self, client: TestClient) -> None:
        """Non-full prompt mode falls back to default ratio (0.5), matching tuning skip.

        factory._apply_small_model_tuning only applies for prompt_mode == "full",
        so a WEAK-window model under lean mode uses the default 0.5 threshold.
        """
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 9000,
                "prompt_mode": "lean",
                "models": [
                    {"model": "custom/mystery-model", "max_input_tokens": 16000}
                ],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        # default ratio -> 0.5 * 16000 = 8000; estimated 9000 >= 8000 -> will compress
        assert item["compress_threshold"] == 8000
        assert item["will_compress"] is True

    def test_prompt_mode_lean_below_default_threshold(self, client: TestClient) -> None:
        """Under lean mode, default 0.5 threshold means smaller sessions don't warn."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 7000,
                "prompt_mode": "lean",
                "models": [
                    {"model": "custom/mystery-model", "max_input_tokens": 16000}
                ],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        assert item["compress_threshold"] == 8000
        assert item["will_compress"] is False

    def test_prompt_mode_full_still_infers_tier(self, client: TestClient) -> None:
        """Explicit full prompt mode still applies tier inference (WEAK -> 0.30)."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 9000,
                "prompt_mode": "full",
                "models": [
                    {"model": "custom/mystery-model", "max_input_tokens": 16000}
                ],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        expected = int(16000 * (0.30 + (0.95 - 0.30) / 3.0))
        assert item["compress_threshold"] == expected

    def test_turn_count_low_session_keeps_static_threshold(
        self, client: TestClient
    ) -> None:
        """Fewer than 5 turns keeps the static threshold (dynamic only kicks in later)."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 6000,
                "turn_count": 3,
                "models": [
                    {"model": "custom/mystery-model", "max_input_tokens": 16000}
                ],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        # WEAK tier -> ratio 0.30 -> static threshold 8266; turn_count < 5 keeps it unchanged
        expected = int(16000 * (0.30 + (0.95 - 0.30) / 3.0))
        assert item["compress_threshold"] == expected
        assert item["will_compress"] is False

    def test_turn_count_long_tight_session_lowers_threshold(
        self, client: TestClient
    ) -> None:
        """Long tight sessions lower the dynamic threshold -> previously-missed compression now warned."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 8000,
                "turn_count": 10,
                "models": [
                    {"model": "custom/mystery-model", "max_input_tokens": 16000}
                ],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        # Static would be 8266 (8000 < 8266 -> no warn); dynamic tightens to 4959 -> warn
        assert item["compress_threshold"] < 8266
        assert item["will_compress"] is True

    def test_turn_count_omitted_keeps_static_behavior(self, client: TestClient) -> None:
        """Absent turn_count keeps the previous static-threshold behavior (backward compatible)."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 6000,
                "models": [
                    {"model": "custom/mystery-model", "max_input_tokens": 16000}
                ],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        expected = int(16000 * (0.30 + (0.95 - 0.30) / 3.0))
        assert item["compress_threshold"] == expected
        assert item["will_compress"] is False
