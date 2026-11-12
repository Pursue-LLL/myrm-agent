"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- BlueprintLocaleSupplement: per-locale title, description and prompt template of one blueprint
- BLUEPRINT_UI_LOCALES: UI locale codes the blueprint texts cover (en, zh, ja, de, ko)

[POS]
蓝图 i18n 子包共用类型；不包含任何具体文案。
"""

from __future__ import annotations

from typing import TypedDict


class BlueprintLocaleSupplement(TypedDict):
    title: dict[str, str]
    description: dict[str, str]
    prompt_template: dict[str, str]


BLUEPRINT_UI_LOCALES: tuple[str, ...] = ("en", "zh", "ja", "de", "ko")
