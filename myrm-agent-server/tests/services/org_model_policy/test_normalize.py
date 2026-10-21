"""Tests for org model policy pattern normalization."""

import pytest

from app.services.org_model_policy.normalize import (
    OrgModelPolicyPatternError,
    normalize_org_model_policy_pattern,
)


def test_slug_glob_gets_prefix() -> None:
    assert normalize_org_model_policy_pattern("deepseek-*") == "*/deepseek-*"


def test_provider_pattern_unchanged() -> None:
    assert normalize_org_model_policy_pattern("openai/*") == "openai/*"


def test_empty_rejected() -> None:
    with pytest.raises(OrgModelPolicyPatternError):
        normalize_org_model_policy_pattern("  ")
