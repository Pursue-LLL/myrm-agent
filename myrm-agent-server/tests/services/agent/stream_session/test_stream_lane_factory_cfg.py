"""Tests for config helpers in stream_lane_factory."""

from __future__ import annotations

import pytest

from app.services.agent.stream_session.stream_lane_factory import _cfg_int_or_none


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
