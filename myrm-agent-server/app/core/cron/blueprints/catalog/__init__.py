"""内置蓝图目录：四个主题模块按声明顺序拼接。"""

from app.core.cron.blueprints.catalog.daily import BLUEPRINTS as DAILY
from app.core.cron.blueprints.catalog.finance import BLUEPRINTS as FINANCE
from app.core.cron.blueprints.catalog.knowledge import BLUEPRINTS as KNOWLEDGE
from app.core.cron.blueprints.catalog.marketing import BLUEPRINTS as MARKETING

__all__ = ["DAILY", "FINANCE", "KNOWLEDGE", "MARKETING"]
