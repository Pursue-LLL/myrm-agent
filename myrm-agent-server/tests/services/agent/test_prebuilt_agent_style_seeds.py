"""Prebuilt agent seeds declare no style field; the four that used one carry its text in their system prompt."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_SEED_DIR = Path(__file__).resolve().parents[3] / "assets" / "prebuilt_agents"

_CREATIVE = "Think outside the box."
_FRIENDLY = "Be warm, friendly, and encouraging."

# Seed label ("<file stem>" or "<file stem>:<member role>") -> the style text its system prompt must carry once.
_STYLED: dict[str, str] = {
    "storefront_shopper_agent": _FRIENDLY,
    "content_creation_squad:writer": _CREATIVE,
    "content_creation_squad:illustrator": _CREATIVE,
    "customer_service_squad:faq_specialist": _FRIENDLY,
}


def _system_prompts() -> dict[str, str]:
    prompts: dict[str, str] = {}
    for path in sorted(_SEED_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data.get("system_prompt"), str):
            prompts[path.stem] = data["system_prompt"]
        for member in data.get("members") or []:
            prompts[f"{path.stem}:{member['role']}"] = member["system_prompt"]
    return prompts


_PROMPTS = _system_prompts()


def test_no_seed_declares_a_style_field() -> None:
    declaring = [path.name for path in _SEED_DIR.glob("*.yaml") if "personality_style" in path.read_text(encoding="utf-8")]

    assert not declaring


@pytest.mark.parametrize(("label", "style_text"), sorted(_STYLED.items()))
def test_styled_seed_carries_its_style_text_once(label: str, style_text: str) -> None:
    assert _PROMPTS[label].count(style_text) == 1


def test_other_seeds_carry_no_style_text() -> None:
    carrying = [label for label, prompt in _PROMPTS.items() if label not in _STYLED and (_CREATIVE in prompt or _FRIENDLY in prompt)]

    assert not carrying
