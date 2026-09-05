"""Tests for composite gateway model fallback and attribution headers."""

from __future__ import annotations

from app.api.integrations.llms import _try_get_model_info_exact


def test_try_get_model_info_exact_direct_hit() -> None:
    # Exact standard model
    info = _try_get_model_info_exact("gpt-4o")
    assert info is not None
    assert isinstance(info, dict)


def test_try_get_model_info_exact_composite_gateway_fallback() -> None:
    # Composite name with gateway vendor prefix
    info = _try_get_model_info_exact("openai/gpt-4o")
    assert info is not None
    assert isinstance(info, dict)


def test_try_get_model_info_exact_unknown_model_returns_none() -> None:
    info = _try_get_model_info_exact("completely_non_existent_fake_model_xyz_999")
    assert info is None
