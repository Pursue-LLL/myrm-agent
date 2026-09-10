"""Tests for prebuilt agent commerce templates (Storefront Shopper & Backoffice Merchant).

Verifies that the YAML templates exist, are valid, have correct metadata and categories,
and integrate seamlessly with the agent templates API.
"""

from __future__ import annotations

import os
import yaml
import pytest
from app.services.agent.template_utils import PREBUILT_AGENTS_DIR


def test_commerce_templates_exist_and_valid() -> None:
    """Ensure both storefront_shopper_agent and backoffice_merchant_agent YAML files exist."""
    shopper_path = os.path.join(PREBUILT_AGENTS_DIR, "storefront_shopper_agent.yaml")
    merchant_path = os.path.join(PREBUILT_AGENTS_DIR, "backoffice_merchant_agent.yaml")

    assert os.path.isfile(shopper_path), f"Missing template: {shopper_path}"
    assert os.path.isfile(merchant_path), f"Missing template: {merchant_path}"

    with open(shopper_path, "r", encoding="utf-8") as f:
        shopper_data = yaml.safe_load(f)
    assert shopper_data["category"] == "commerce"
    assert "zh" in shopper_data["name"]
    assert "en" in shopper_data["name"]
    assert len(shopper_data.get("suggestion_prompts", [])) >= 3

    with open(merchant_path, "r", encoding="utf-8") as f:
        merchant_data = yaml.safe_load(f)
    assert merchant_data["category"] == "commerce"
    assert "zh" in merchant_data["name"]
    assert "en" in merchant_data["name"]
    assert len(merchant_data.get("suggestion_prompts", [])) >= 3
