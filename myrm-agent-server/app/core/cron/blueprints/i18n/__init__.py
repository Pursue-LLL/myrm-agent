"""[INPUT]
- app.core.cron.blueprints.i18n.daily::SUPPLEMENTAL_BY_ID (POS: 蓝图 i18n 子包的一部分；由 __init__.py 合并。)
- app.core.cron.blueprints.i18n.finance::SUPPLEMENTAL_BY_ID (POS: 蓝图 i18n 子包的一部分；由 __init__.py 合并。)
- app.core.cron.blueprints.i18n.growth::SUPPLEMENTAL_BY_ID (POS: 蓝图 i18n 子包的一部分；由 __init__.py 合并。)
- app.core.cron.blueprints.i18n.knowledge::SUPPLEMENTAL_BY_ID (POS: 蓝图 i18n 子包的一部分；由 __init__.py 合并。)
- app.core.cron.blueprints.i18n.types::BLUEPRINT_UI_LOCALES / BlueprintLocaleSupplement (POS: 蓝图 i18n 子包共用类型；不包含任何具体文案。)

[OUTPUT]
- SUPPLEMENTAL_BY_ID: ja/de/ko title, description and prompt template of each blueprint, keyed by blueprint id and merged from the topic modules
- BLUEPRINT_UI_LOCALES
- BlueprintLocaleSupplement

[POS]
`app.core.cron.blueprints.i18n` 的唯一入口；按主题分组的文案在子模块中定义。
"""

from app.core.cron.blueprints.i18n.daily import SUPPLEMENTAL_BY_ID as _DAILY
from app.core.cron.blueprints.i18n.finance import SUPPLEMENTAL_BY_ID as _FINANCE
from app.core.cron.blueprints.i18n.growth import SUPPLEMENTAL_BY_ID as _GROWTH
from app.core.cron.blueprints.i18n.knowledge import SUPPLEMENTAL_BY_ID as _KNOWLEDGE
from app.core.cron.blueprints.i18n.types import BLUEPRINT_UI_LOCALES, BlueprintLocaleSupplement

SUPPLEMENTAL_BY_ID: dict[str, BlueprintLocaleSupplement] = {
    **_DAILY,
    **_FINANCE,
    **_KNOWLEDGE,
    **_GROWTH,
}

__all__ = ["BLUEPRINT_UI_LOCALES", "SUPPLEMENTAL_BY_ID", "BlueprintLocaleSupplement"]
