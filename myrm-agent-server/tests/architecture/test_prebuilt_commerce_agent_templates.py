"""Architecture and contract tests for prebuilt commerce agent templates.

Validates:
1. storefront_shopper_agent and backoffice_merchant_agent templates exist.
2. Complete bilingual metadata (zh and en for name and description).
3. Category is strictly set to 'commerce'.
4. System prompts define commerce-specific governance principles (OPTIONS_GATE, GUARDRAIL_GATE).
5. Suggestion prompts are non-empty for visual wizard instantiation.
"""

from pathlib import Path
import yaml
from app.services.agent.template_utils import PREBUILT_AGENTS_DIR, resolve_i18n


def test_commerce_agent_templates_exist_and_valid() -> None:
    expected_templates = {
        "storefront_shopper_agent.yaml": {
            "category": "commerce",
            "required_prompt_keywords": ["OPTIONS_GATE", "Option"],
        },
        "backoffice_merchant_agent.yaml": {
            "category": "commerce",
            "required_prompt_keywords": ["GUARDRAIL_GATE", "Staged"],
        },
    }

    for filename, meta in expected_templates.items():
        file_path = Path(PREBUILT_AGENTS_DIR) / filename
        assert file_path.exists(), f"Commerce preset template {filename} does not exist at {file_path}"

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert isinstance(data, dict), f"{filename} root must be a dictionary"
        assert data.get("category") == meta["category"], f"{filename} category must be {meta['category']}"
        assert data.get("agent_type") == "individual"

        # Bilingual name verification
        name = data.get("name")
        assert isinstance(name, dict), f"{filename} name must be a bilingual dictionary"
        assert name.get("zh"), f"{filename} missing Chinese name"
        assert name.get("en"), f"{filename} missing English name"

        # Bilingual description verification
        desc = data.get("description")
        assert isinstance(desc, dict), f"{filename} description must be a bilingual dictionary"
        assert desc.get("zh"), f"{filename} missing Chinese description"
        assert desc.get("en"), f"{filename} missing English description"

        # System prompt domain verification
        system_prompt = data.get("system_prompt", "")
        for kw in meta["required_prompt_keywords"]:
            assert kw.lower() in system_prompt.lower(), f"{filename} system_prompt missing key term {kw}"

        # Suggestions prompts
        suggestions = data.get("suggestion_prompts", [])
        assert len(suggestions) >= 2, f"{filename} must provide at least 2 suggestion prompts for WebUI wizard"

        # resolve_i18n resolution verification
        zh_name = resolve_i18n(name, "zh")
        en_name = resolve_i18n(name, "en")
        assert zh_name != en_name
        assert zh_name == name["zh"]
        assert en_name == name["en"]
