"""[INPUT]
- app.core.cron.blueprints.catalog.daily::BLUEPRINTS (POS: Cron 蓝图目录的一部分；由 app/core/cron/blueprints/ 的注册表按声明顺序拼成内置清单。)
- app.core.cron.blueprints.catalog.finance::BLUEPRINTS (POS: Cron 蓝图目录的一部分；由 app/core/cron/blueprints/ 的注册表按声明顺序拼成内置清单。)
- app.core.cron.blueprints.catalog.knowledge::BLUEPRINTS (POS: Cron 蓝图目录的一部分；由 app/core/cron/blueprints/ 的注册表按声明顺序拼成内置清单。)
- app.core.cron.blueprints.catalog.marketing::BLUEPRINTS (POS: Cron 蓝图目录的一部分；由 app/core/cron/blueprints/ 的注册表按声明顺序拼成内置清单。)

[OUTPUT]
- DAILY
- FINANCE
- KNOWLEDGE
- MARKETING

[POS]
内置蓝图目录：四个主题模块按声明顺序拼接。
"""

from app.core.cron.blueprints.catalog.daily import BLUEPRINTS as DAILY
from app.core.cron.blueprints.catalog.finance import BLUEPRINTS as FINANCE
from app.core.cron.blueprints.catalog.knowledge import BLUEPRINTS as KNOWLEDGE
from app.core.cron.blueprints.catalog.marketing import BLUEPRINTS as MARKETING

__all__ = ["DAILY", "FINANCE", "KNOWLEDGE", "MARKETING"]
