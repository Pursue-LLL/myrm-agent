"""Tests for config helpers in stream_lane_factory."""

from __future__ import annotations

from unittest.mock import patch

from app.services.agent.stream_session.stream_lane_factory import _cfg_int_or_none, _inject_wu_consumed


class TestCfgIntOrNone:
    """_cfg_int_or_none must return positive int or None — never zero, negative, or junk."""

    def test_valid_positive_int(self):
        assert _cfg_int_or_none({"k": 600}, "k") == 600

    def test_valid_positive_str(self):
        assert _cfg_int_or_none({"k": "800"}, "k") == 800

    def test_zero_returns_none(self):
        assert _cfg_int_or_none({"k": 0}, "k") is None

    def test_negative_returns_none(self):
        assert _cfg_int_or_none({"k": -100}, "k") is None

    def test_empty_string_returns_none(self):
        assert _cfg_int_or_none({"k": ""}, "k") is None

    def test_missing_key_returns_none(self):
        assert _cfg_int_or_none({}, "k") is None

    def test_none_value_returns_none(self):
        assert _cfg_int_or_none({"k": None}, "k") is None

    def test_non_numeric_string_returns_none(self):
        assert _cfg_int_or_none({"k": "abc"}, "k") is None

    def test_float_truncates_to_int(self):
        assert _cfg_int_or_none({"k": 600.9}, "k") == 600

    def test_boundary_one(self):
        assert _cfg_int_or_none({"k": 1}, "k") == 1


class TestInjectWuConsumed:
    """_inject_wu_consumed attaches wu_consumed only in sandbox mode with valid cost."""

    @patch("app.config.deploy_mode.is_sandbox", return_value=True)
    @patch("app.config.settings.get_settings")
    def test_sandbox_with_cost(self, mock_settings, _mock_sandbox):
        mock_settings.return_value.control_plane.platform_wu_per_usd = 1000.0
        chunk: dict[str, object] = {"type": "message_end", "cost_usd": 0.05}
        _inject_wu_consumed(chunk)
        assert chunk["wu_consumed"] == 50

    @patch("app.config.deploy_mode.is_sandbox", return_value=True)
    @patch("app.config.settings.get_settings")
    def test_minimum_1_wu(self, mock_settings, _mock_sandbox):
        mock_settings.return_value.control_plane.platform_wu_per_usd = 1000.0
        chunk: dict[str, object] = {"type": "message_end", "cost_usd": 0.0001}
        _inject_wu_consumed(chunk)
        assert chunk["wu_consumed"] == 1

    @patch("app.config.deploy_mode.is_sandbox", return_value=False)
    def test_local_mode_skipped(self, _mock_sandbox):
        chunk: dict[str, object] = {"type": "message_end", "cost_usd": 0.05}
        _inject_wu_consumed(chunk)
        assert "wu_consumed" not in chunk

    @patch("app.config.deploy_mode.is_sandbox", return_value=True)
    def test_zero_cost_skipped(self, _mock_sandbox):
        chunk: dict[str, object] = {"type": "message_end", "cost_usd": 0.0}
        _inject_wu_consumed(chunk)
        assert "wu_consumed" not in chunk

    @patch("app.config.deploy_mode.is_sandbox", return_value=True)
    def test_missing_cost_skipped(self, _mock_sandbox):
        chunk: dict[str, object] = {"type": "message_end"}
        _inject_wu_consumed(chunk)
        assert "wu_consumed" not in chunk
