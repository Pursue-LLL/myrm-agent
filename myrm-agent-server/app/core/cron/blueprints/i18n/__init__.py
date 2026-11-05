"""蓝图 ja/de/ko 补充文案门面。

[OUTPUT]
SUPPLEMENTAL_BY_ID / BLUEPRINT_UI_LOCALES / BlueprintLocaleSupplement

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
