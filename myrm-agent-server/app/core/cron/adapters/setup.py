"""App-layer assembly: creates framework CronScheduler + CronManager with concrete backends.

Single integration point between app layer and framework cron toolkit.

Usage::

    from app.core.cron.adapters.setup import create_cron_manager, get_cron_scheduler

    # At startup (FastAPI lifespan):
    scheduler = get_cron_scheduler()
    await scheduler.start()

    # In agent tool creation:
    manager = get_cron_manager()
    tools = create_cron_tools(manager, user_id)
"""

from __future__ import annotations

import logging
from myrm_agent_harness.toolkits.cron import (
    CronConfig,
    CronManager,
    CronScheduler,
    DeliveryConfig,
    JobType,
    RouterJobRunner,
    ShellJobRunner,
)
from myrm_agent_harness.toolkits.cron.protocols import JobRunner

from app.config.deploy_mode import is_local_mode
from app.core.cron.adapters.agent_runner import AgentJobRunner
from app.core.cron.adapters.entitlement_guarded_manager import EntitlementGuardedCronManager
from app.core.cron.adapters.channel_delivery import ChannelResultDelivery
from app.core.cron.adapters.python_condition import SandboxedPythonCondition
from app.core.cron.adapters.situation_sections import build_situation_report_builder
from app.core.cron.adapters.sqlalchemy_store import SqlAlchemyCronStore
from app.core.cron.adapters.sqlalchemy_trigger_provider import SqlAlchemyTriggerProvider

logger = logging.getLogger(__name__)

_scheduler: CronScheduler | None = None
_manager: EntitlementGuardedCronManager | None = None
_store: SqlAlchemyCronStore | None = None


def get_cron_scheduler() -> CronScheduler:
    """Get or create the process-level CronScheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = _build_scheduler()
    return _scheduler


def get_cron_store() -> SqlAlchemyCronStore:
    """Get or create the SqlAlchemyCronStore singleton."""
    global _store
    if _store is None:
        _store = SqlAlchemyCronStore()
    return _store


def get_cron_manager() -> EntitlementGuardedCronManager:
    """Get or create the entitlement-guarded CronManager singleton."""
    global _manager
    if _manager is None:
        inner = CronManager(
            store=get_cron_store(),
            scheduler=get_cron_scheduler(),
            shell_enabled=is_local_mode(),
        )
        _manager = EntitlementGuardedCronManager(inner)
    return _manager


async def _push_callback(user_id: str, job_name: str, text: str, level: str) -> None:
    from app.core.cron.push_store import PushLevel, push

    await push(user_id, job_name, text, PushLevel(level))


def _build_scheduler() -> CronScheduler:
    store = get_cron_store()
    runners = _build_runners()
    delivery = ChannelResultDelivery()
    config = _build_cron_config()

    from app.core.cron.adapters.memory_lock import CrossProcessCronLock

    return CronScheduler(
        store=store,
        runners=runners,
        delivery=delivery,
        config=config,
        lock=CrossProcessCronLock(),
        push_callback=_push_callback,
        trigger_provider=SqlAlchemyTriggerProvider(),
        pre_condition=SandboxedPythonCondition(timeout_seconds=60),
    )


def _build_cron_config() -> CronConfig:
    """Build global cron configuration from environment variables."""
    failure_delivery: DeliveryConfig | None = None
    from app.config.settings import settings

    url = settings.services.cron_failure_webhook_url.strip()
    if url:
        logger.warning("Global cron failure delivery configured: webhook -> %s", url[:50])
        failure_delivery = DeliveryConfig(channel="webhook", target=url)

    return CronConfig(failure_delivery=failure_delivery)


def _build_runners() -> dict[JobType, JobRunner]:
    situation_builder = build_situation_report_builder()
    runners: dict[JobType, JobRunner] = {
        JobType.AGENT: AgentJobRunner(situation_builder=situation_builder),
        JobType.ROUTER: RouterJobRunner(),
    }
    if is_local_mode():
        runners[JobType.SHELL] = ShellJobRunner()
    return runners


