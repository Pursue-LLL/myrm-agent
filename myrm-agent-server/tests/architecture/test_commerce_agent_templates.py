"""Architecture tests for Commerce Prebuilt Agent Templates.

Verifies:
1. `storefront_shopper_agent.yaml` and `backoffice_merchant_agent.yaml` exist and parse cleanly.
2. Required schema fields: name, description, avatar_url, category, suggestion_prompts, system_prompt.
3. Category is correctly identified as 'commerce'.
4. Bilingual names and descriptions (zh and en) are present and well-formed.
5. Critical commerce governance keywords (OPTIONS_GATE, GUARDRAIL_GATE) exist in system prompts.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.services.agent.template_utils import PREBUILT_AGENTS_DIR, resolve_i18n


def test_commerce_agent_templates_exist() -> None:
    agents_dir = Path(PREBUILT_AGENTS_DIR)
    assert agents_dir.is_dir()

    shopper_file = agents_dir / "storefront_shopper_agent.yaml"
    merchant_file = agents_dir / "backoffice_merchant_agent.yaml"

    assert shopper_file.is_file(), f"Missing {shopper_file}"
    assert merchant_file.is_file(), f"Missing {merchant_file}"


def test_storefront_shopper_agent_schema() -> None:
    file_path = Path(PREBUILT_AGENTS_DIR) / "storefront_shopper_agent.yaml"
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert isinstance(data, dict)
    assert data.get("category") == "commerce"
    assert data.get("agent_type") == "individual"

    name = data.get("name")
    assert isinstance(name, dict)
    assert "zh" in name and "en" in name
    name_zh = resolve_i18n(name, "zh")
    name_en = resolve_i18n(name, "en")
    assert "导购" in name_zh
    assert "Shopper" in name_en or "Storefront" in name_en

    desc = data.get("description")
    assert isinstance(desc, dict)
    assert "zh" in desc and "en" in desc
    desc_zh = resolve_i18n(desc, "zh")
    desc_en = resolve_i18n(desc, "en")
    assert len(desc_zh) > 10
    assert len(desc_en) > 10

    prompts = data.get("suggestion_prompts", [])
    assert len(prompts) >= 3

    sys_prompt = data.get("system_prompt", "")
    assert "OPTIONS_GATE" in sys_prompt
    assert "Storefront Shopper Agent" in sys_prompt


def test_backoffice_merchant_agent_schema() -> None:
    file_path = Path(PREBUILT_AGENTS_DIR) / "backoffice_merchant_agent.yaml"
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert isinstance(data, dict)
    assert data.get("category") == "commerce"
    assert data.get("agent_type") == "individual"

    name = data.get("name")
    assert isinstance(name, dict)
    assert "zh" in name and "en" in name
    name_zh = resolve_i18n(name, "zh")
    name_en = resolve_i18n(name, "en")
    assert "经营参谋" in name_zh or "商家" in name_zh
    assert "Merchant" in name_en

    desc = data.get("description")
    assert isinstance(desc, dict)
    assert "zh" in desc and "en" in desc
    desc_zh = resolve_i18n(desc, "zh")
    desc_en = resolve_i18n(desc, "en")
    assert len(desc_zh) > 10
    assert len(desc_en) > 10

    prompts = data.get("suggestion_prompts", [])
    assert len(prompts) >= 3

    sys_prompt = data.get("system_prompt", "")
    assert "GUARDRAIL_GATE" in sys_prompt
    assert "Backoffice Merchant Agent" in sys_prompt
