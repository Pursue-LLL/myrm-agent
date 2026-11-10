"""Tests for model switch preflight endpoint.

Covers:
- POST /api/v1/integrations/llm/model-switch-preflight response schema
- Threshold computation matches harness ContextConfig formula
- Default thresholds (50% of the window) when no compress_start_ratio is given, whatever the model name
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
        """Frontend-provided window drives threshold even when the catalog does not know the model."""
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
        # no ratio -> default threshold = 50% of the window
        assert item["compress_threshold"] == 8000
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
        """An explicit ratio replaces the default thresholds and follows the ContextConfig formula."""
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

    @pytest.mark.parametrize("window", [8_192, 32_000, 200_000])
    def test_default_threshold_is_half_the_window(self, client: TestClient, window: int) -> None:
        """Without an explicit ratio every window size, small or large, uses the same default: 50% of the window."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": window // 2,
                "models": [{"model": "custom/any-model", "max_input_tokens": window}],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        assert item["compress_threshold"] == window // 2
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
        # 16000 -> threshold 8000 -> will compress
        assert by_model["custom/a"]["will_compress"] is True
        # 100000 -> threshold 50000 -> no compress
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
        # default static threshold 8000; turn_count < 5 keeps it unchanged
        assert item["compress_threshold"] == 8000
        assert item["will_compress"] is False

    def test_turn_count_long_tight_session_lowers_threshold(self, client: TestClient) -> None:
        """Long tight sessions lower the dynamic threshold -> previously-missed compression now warned."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 7500,
                "turn_count": 10,
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        # Static would be 8000 (7500 < 8000 -> no warn); dynamic tightens to 4800 -> warn
        assert item["compress_threshold"] < 8000
        assert item["will_compress"] is True

    def test_turn_count_omitted_keeps_static_behavior(self, client: TestClient) -> None:
        """Absent turn_count uses the static threshold."""
        response = client.post(
            "/api/v1/integrations/llm/model-switch-preflight",
            json={
                "estimated_tokens": 6000,
                "models": [{"model": "custom/mystery-model", "max_input_tokens": 16000}],
            },
        )
        assert response.status_code == 200
        item = response.json()["data"]["results"][0]
        assert item["compress_threshold"] == 8000
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
        # threshold 8000; 9000 >= 8000 -> would compress
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
            "app.api.integrations.llms.preflight.model_facts",
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

    def test_backend_resolves_window_from_catalog_info(self, client: TestClient) -> None:
        """Backend resolves max_input_tokens from the model catalog when not provided."""
        with patch(
            "app.api.integrations.llms.preflight.model_facts",
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
        # default threshold = 50% of the 32k window, however the model is named
        assert item["compress_threshold"] == 16000

    def test_backend_does_not_read_max_tokens_as_a_window(self, client: TestClient) -> None:
        """max_tokens is an output budget for part of the catalog, never a context window."""
        with patch(
            "app.api.integrations.llms.preflight.model_facts",
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
        assert item["found"] is False
        assert item["new_window"] is None

    def test_backend_ignores_nonpositive_windows(self, client: TestClient) -> None:
        """A non-positive window resolves to None -> found=False."""
        with patch(
            "app.api.integrations.llms.preflight.model_facts",
            return_value={"max_input_tokens": 0},
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
