"""
配置健康监控服务
定期检查 LLM provider 配置的健康状态，主动发现问题
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 健康检查间隔（秒）
HEALTH_CHECK_INTERVAL_SECONDS = 3600  # 1小时

# 全局任务引用
_health_check_task: asyncio.Task[None] | None = None


async def check_provider_health(db: "AsyncSession", user_id: str) -> dict[str, object]:
    """
    检查单个用户的 provider 配置健康状态

    Args:
        db: 数据库会话
        user_id: 用户ID

    Returns:
        健康检查结果
    """
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.config_readiness import ProviderConfigChecker

    _ = db, user_id  # session / id reserved for future multi-tenant use
    configs = await load_user_configs()
    raw = configs.personal_settings_dict
    config_json = raw if isinstance(raw, dict) else None

    if not config_json:
        return {
            "user_id": user_id,
            "healthy": False,
            "reason": "no_config",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    checker = ProviderConfigChecker()
    readiness = checker.check(config_json)

    return {
        "user_id": user_id,
        "healthy": readiness.is_ready,
        "missing_items": readiness.missing_items,
        "suggestions": readiness.suggestions,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def check_all_users_health(db: "AsyncSession") -> list[dict[str, object]]:
    """
    检查所有用户的配置健康状态

    Args:
        db: 数据库会话

    Returns:
        所有用户的健康检查结果列表
    """
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    user_ids = ["sandbox"]

    results = []
    event_bus = get_event_bus()

    for user_id in user_ids:
        try:
            health = await check_provider_health(db, user_id)
            results.append(health)

            # 如果发现问题，记录日志并推送SSE通知
            if not health.get("healthy"):
                logger.warning(
                    "User %s has unhealthy provider config: %s",
                    health.get("missing_items"),
                )

                # 推送SSE通知给前端
                event_bus.publish(
                    AppEvent(
                        event_type=AppEventType.CONFIG_HEALTH_WARNING,
                        data={
                            "user_id": user_id,
                            "missing_items": health.get("missing_items") or [],
                            "suggestions": health.get("suggestions") or [],
                            "checked_at": health.get("checked_at", ""),
                        },
                    )
                )
        except Exception as e:
            logger.error("Failed to check health for user %s: %s", e)
            results.append(
                {
                    "user_id": user_id,
                    "healthy": False,
                    "reason": "check_failed",
                    "error": str(e),
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    return results


async def health_check_loop() -> None:
    """
    后台定期健康检查循环
    每小时检查一次所有用户的配置健康状态
    """
    from app.database.connection import get_session

    logger.info("Config health check loop started (interval: %ds)", HEALTH_CHECK_INTERVAL_SECONDS)

    while True:
        try:
            await asyncio.sleep(HEALTH_CHECK_INTERVAL_SECONDS)

            logger.debug("Running periodic config health check...")
            async with get_session() as db:
                results = await check_all_users_health(db)

            unhealthy_count = sum(1 for r in results if not r.get("healthy"))
            logger.info(
                "Health check completed: %d users checked, %d unhealthy",
                len(results),
                unhealthy_count,
            )

        except asyncio.CancelledError:
            logger.info("Health check loop cancelled")
            break
        except Exception as e:
            logger.error("Health check loop error: %s", e)
            # 发生错误时继续运行，等待下一次检查


def start_health_monitor() -> None:
    """启动健康监控后台任务"""
    global _health_check_task

    if _health_check_task is not None and not _health_check_task.done():
        logger.warning("Health monitor already running")
        return

    _health_check_task = asyncio.create_task(health_check_loop())
    logger.info("Health monitor started")


def stop_health_monitor() -> None:
    """停止健康监控后台任务"""
    global _health_check_task

    if _health_check_task is not None and not _health_check_task.done():
        _health_check_task.cancel()
        logger.info("Health monitor stopped")


__all__ = [
    "check_provider_health",
    "check_all_users_health",
    "start_health_monitor",
    "stop_health_monitor",
]
