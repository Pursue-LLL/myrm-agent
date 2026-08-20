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
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
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
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
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
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 32000}],
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

    def test_out_of_range_compress_start_ratio_is_clamped(self, client: TestClient) -> None:
        """Out-of-range ratio is clamped by harness ContextConfig instead of rejected.

        Mirrors runtime behavior: ContextConfig._effective_ratio clamps to [0.20, 0.85].
        """
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 10000,
                "compress_start_ratio": 1.5,
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
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
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
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
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
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
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
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
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        expected = int(16000 * (0.30 + (0.95 - 0.30) / 3.0))
        assert item["compress_threshold"] == expected

    def test_turn_count_low_session_keeps_static_threshold(self, client: TestClient) -> None:
        """Fewer than 5 turns keeps the static threshold (dynamic only kicks in later)."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 6000,
                "turn_count": 3,
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        # WEAK tier -> ratio 0.30 -> static threshold 8266; turn_count < 5 keeps it unchanged
        expected = int(16000 * (0.30 + (0.95 - 0.30) / 3.0))
        assert item["compress_threshold"] == expected
        assert item["will_compress"] is False

    def test_turn_count_long_tight_session_lowers_threshold(self, client: TestClient) -> None:
        """Long tight sessions lower the dynamic threshold -> previously-missed compression now warned."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 8000,
                "turn_count": 10,
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
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
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        expected = int(16000 * (0.30 + (0.95 - 0.30) / 3.0))
        assert item["compress_threshold"] == expected
        assert item["will_compress"] is False


class TestPreflightAntiThrashStreak:
    """Preflight consumes compression ineffective streak (runtime anti-thrash parity)."""

    @pytest.fixture(autouse=True)
    def streak_store(self) -> Iterator[_FakeStreakStore]:
        """Provide a fresh fake streak store per test, isolated from other tests."""
        store = _FakeStreakStore()
        with patch(
            "myrm_agent_harness.agent.context_management.strategies.compression.compression_streak_store.get_compression_streak_store",
            return_value=store,
        ):
            yield store

    def _post(self, client: TestClient, *, estimated_tokens: int, chat_id: str) -> dict:
        return client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": estimated_tokens,
                "chat_id": chat_id,
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
            },
        ).json()["data"]["results"][0]

    def test_streak_below_limit_keeps_normal_judgment(self, client: TestClient, streak_store: _FakeStreakStore) -> None:
        """streak=1 (< limit 2) does not suppress the warning."""
        streak_store.set_streak("chat-a", 1)
        item = self._post(client, estimated_tokens=9000, chat_id="chat-a")
        # WEAK tier -> threshold ~8266; 9000 >= 8266 -> would compress
        assert item["will_compress"] is True

    def test_streak_at_limit_below_safety_net_suppresses_warning(
        self, client: TestClient, streak_store: _FakeStreakStore
    ) -> None:
        """streak>=2 with tokens<90% window: runtime skips compression, preflight must not warn."""
        streak_store.set_streak("chat-a", 2)
        item = self._post(client, estimated_tokens=9000, chat_id="chat-a")
        # 9000 < 16000*0.9=14400 and streak>=2 -> anti-thrash blocks -> no warning
        assert item["will_compress"] is False

    def test_streak_at_limit_above_safety_net_still_warns(self, client: TestClient, streak_store: _FakeStreakStore) -> None:
        """streak>=2 but tokens>=90% window: runtime force-compresses (OOM guard), warning stays."""
        streak_store.set_streak("chat-a", 2)
        item = self._post(client, estimated_tokens=15000, chat_id="chat-a")
        # 15000 >= 14400 (90% window) -> safety net overrides anti-thrash -> warns
        assert item["will_compress"] is True

    def test_no_chat_id_ignores_streak(self, client: TestClient) -> None:
        """Absent chat_id keeps previous behavior (no streak lookup, no suppression)."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 9000,
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        assert item["will_compress"] is True


class _FakeStreakStore:
    """Minimal harness CompressionStreakStore stub for preflight tests."""

    def __init__(self) -> None:
        self._data: dict[str, int] = {}

    def get_streak(self, chat_id: str | None) -> int:
        if not chat_id:
            return 0
        return self._data.get(chat_id, 0)

    def set_streak(self, chat_id: str | None, streak: int) -> None:
        if chat_id:
            self._data[chat_id] = max(0, int(streak))


class TestPreflightWindowResolution:
    """Window resolution edge cases in _resolve_target_max_input_tokens."""

    def test_missing_window_skips_warning(self, client: TestClient) -> None:
        """No frontend window and unknown model -> found=False, no warning."""
        with patch(
            "app.api.integrations.llms._try_get_model_info_exact",
            return_value=None,
        ):
            response = client.post(
                "/api/v1/integrations/llm/model-switch-preflight",
                json={
                    "estimated_tokens": 9000,
                    "models": [{"model": "custom/unknown-no-window"}],
                },
            )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        assert item["found"] is False
        assert item["new_window"] is None
        assert item["will_compress"] is False

    def test_backend_resolves_window_from_litellm_info(self, client: TestClient) -> None:
        """Backend resolves max_input_tokens from LiteLLM model info when not provided."""
        with patch(
            "app.api.integrations.llms._try_get_model_info_exact",
            return_value={"max_input_tokens": 32000},
        ):
            response = client.post(
                "/api/v1/integrations/llm/model-switch-preflight",
                json={
                    "estimated_tokens": 9000,
                    "models": [{"model": "gpt-4o"}],
                },
            )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        assert item["found"] is True
        assert item["new_window"] == 32000
        # gpt-4o 32k -> MEDIUM tier (ratio 0.50) -> threshold = 32000 * (0.50 + 0.15) = 20800
        assert item["compress_threshold"] == 20800

    def test_backend_falls_back_to_max_tokens_key(self, client: TestClient) -> None:
        """max_tokens key is honored when max_input_tokens is absent."""
        with patch(
            "app.api.integrations.llms._try_get_model_info_exact",
            return_value={"max_tokens": 64000},
        ):
            response = client.post(
                "/api/v1/integrations/llm/model-switch-preflight",
                json={
                    "estimated_tokens": 9000,
                    "models": [{"model": "gpt-4o"}],
                },
            )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        assert item["found"] is True
        assert item["new_window"] == 64000

    def test_backend_ignores_nonpositive_windows(self, client: TestClient) -> None:
        """info with only non-positive windows resolves to None -> found=False."""
        with patch(
            "app.api.integrations.llms._try_get_model_info_exact",
            return_value={"max_input_tokens": 0, "max_tokens": -1},
        ):
            response = client.post(
                "/api/v1/integrations/llm/model-switch-preflight",
                json={
                    "estimated_tokens": 9000,
                    "models": [{"model": "gpt-4o"}],
                },
            )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        assert item["found"] is False
        assert item["new_window"] is None
