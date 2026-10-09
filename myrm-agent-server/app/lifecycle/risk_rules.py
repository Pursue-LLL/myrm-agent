"""Startup risk-rule initialization.

[INPUT]
- app.services.risk.rule_service::RiskRuleService (POS: 风险规则业务服务)
- app.services.risk.detection::get_detection_service (POS: 风险检测引擎单例)
- app.platform_utils::get_session_factory (POS: 数据库会话工厂)

[OUTPUT]
- init_risk_rules: 播种内置风险规则并初始化检测引擎（遇并发启动写入方导致的锁库时在新事务上重试）

[POS]
启动编排层的风险规则子模块。与 ``system.py`` 的其余启动任务并发运行，故自带锁库重试。
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_RISK_RULE_INIT_ATTEMPTS = 3
_RISK_RULE_INIT_RETRY_DELAY_SEC = 0.5


async def _seed_and_load_risk_rules() -> None:
    from app.platform_utils import get_session_factory
    from app.services.risk.detection import get_detection_service
    from app.services.risk.rule_service import RiskRuleService

    async with get_session_factory()() as db:
        inserted = await RiskRuleService().seed_builtin_rules(db)
        await db.commit()
        if inserted > 0:
            logger.info("Seeded %d built-in risk rules on startup", inserted)
        await get_detection_service().reload(db)
    logger.info("Risk detection engine initialized")


async def init_risk_rules() -> None:
    """Seed built-in risk rules and initialize the detection engine.

    Seeding reads before it writes, and other startup tasks write at the same time. SQLite aborts such a
    transaction with "database is locked" (SQLITE_BUSY_SNAPSHOT, which ``busy_timeout`` does not cover) when
    one of them commits in between, so a locked database gets a fresh transaction instead of an engine
    that never loaded its rules.
    """
    from sqlalchemy.exc import OperationalError

    for attempt in range(1, _RISK_RULE_INIT_ATTEMPTS + 1):
        try:
            await _seed_and_load_risk_rules()
            return
        except OperationalError as e:
            if attempt == _RISK_RULE_INIT_ATTEMPTS:
                logger.error("Risk rule initialization failed after %d attempts: %s", attempt, e)
                return
            logger.warning("Risk rule initialization hit a locked database (attempt %d), retrying: %s", attempt, e)
            await asyncio.sleep(_RISK_RULE_INIT_RETRY_DELAY_SEC * attempt)
        except Exception as e:
            logger.error("Risk rule initialization failed: %s", e)
            return
