"""蓝图补充文案的类型。

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
