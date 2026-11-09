"""[INPUT]
- .state (POS: shared startup state)

[OUTPUT]
- phase helpers and the sequential/parallel startup phases

[POS]
Startup phases of the server lifespan.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.config.settings import settings
from app.database.connection import init_database
from app.lifecycle import (
    init_allowlist_store,
    init_workspace_trust_store,
)

if TYPE_CHECKING:
    pass

from . import state
from .state import logger


async def _register_db_pool_metrics_task() -> None:
    """Delegate DB pool metrics registration to MonitoringManager."""
    from app.core.monitoring import register_db_pool_metrics

    await register_db_pool_metrics()


async def _dispatch_startup_event() -> None:
    """Dispatch @startup system event so trigger-bound cron jobs can fire on boot."""
    try:
        from app.core.cron.adapters.setup import get_cron_scheduler

        scheduler = get_cron_scheduler()
        if scheduler:
            count = await scheduler.dispatch_system_event(source="app", event_type="startup", payload={})
            if count:
                logger.info("[Startup] @startup trigger fired %d job(s)", count)
    except Exception as e:
        logger.debug("[Startup] @startup event dispatch skipped: %s", e)


async def _preload_agent_tool_layers() -> None:
    """Register server-layer tools off the boot path; the first agent turn awaits the same gate."""
    try:
        from app.ai_agents.general_agent.tools import ensure_tool_layer_bootstrap

        await asyncio.to_thread(ensure_tool_layer_bootstrap)
        logger.info("[Startup] Agent tool layers ready")
    except Exception as exc:
        logger.exception("[Startup] Agent tool layer preload failed: %s", exc)


async def _seed_trunk_templates() -> None:
    """Insert missing trunk templates in the background; boot never waits on it."""
    try:
        from app.services.workflow_templates.service import get_template_store
        from app.services.workflow_templates.trunk_templates import seed_trunk_templates

        def _seed() -> int:
            return len(seed_trunk_templates(get_template_store()))

        ready = await asyncio.to_thread(_seed)
        logger.info("[Startup] Trunk workflow templates ready: %d", ready)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Startup] Trunk template seeding skipped: %s", exc)


def _apply_code_execution_config() -> None:
    """Apply business-layer code execution configuration to the framework."""
    from myrm_agent_harness.toolkits.code_execution.config import (
        ExecutionConfig,
        NetworkConfig,
        set_execution_config,
    )

    ce = settings.code_execution
    allowed_hosts: frozenset[str] | None = None
    if ce.allowed_hosts:
        allowed_hosts = frozenset(h.strip() for h in ce.allowed_hosts.split(",") if h.strip())

    config = ExecutionConfig(
        network=NetworkConfig(
            allow_network=ce.allow_network,
            allowed_hosts=allowed_hosts,
        ),
    )
    set_execution_config(config)
    logger.info(
        "Code execution config applied: allow_network=%s, allowed_hosts=%s",
        ce.allow_network,
        "default" if allowed_hosts is None else len(allowed_hosts),
    )


async def _phase_1a_sequential() -> None:
    """Phase 1a: Sequential critical tasks (DB + dependent tasks)."""
    from app.config.settings import settings
    from app.platform_utils.persistent_root import (
        configure_persistent_root_for_local_dev,
    )

    configure_persistent_root_for_local_dev(settings.database.state_dir)

    # A queued import / restore point is swapped in before any database opens; it never blocks boot.
    try:
        from pathlib import Path

        from app.services.instance_archive import run_pending_promotion

        swap = await asyncio.to_thread(run_pending_promotion, Path(settings.database.state_dir))
        if swap is not None:
            logger.info("[Startup] Instance %s: %s", swap.operation.value, swap.status.value)
    except Exception as swap_exc:  # noqa: BLE001
        logger.error("[Startup] Pending instance swap failed: %s", swap_exc)

    try:
        await init_database()
        logger.info("[Startup] Database initialized")
    except Exception as e:
        logger.error("[Startup] Database initialization failed: %s", e)

        from app.config.settings import settings
        from app.database.operations.recovery import rescue_database
        from app.platform_utils import reset_database_engine
        from app.server.status import system_status

        db_path = settings.database.sqlite_path

        # 1. Try B-Tree page-skipping rowid salvage rescue (last-resort row-level data salvage)
        if rescue_database(db_path):
            system_status.database_recovered = True
            await reset_database_engine()
            await init_database()
            logger.info("[Startup] Database rescued successfully")
        else:
            # 2. Try multi-snapshot integrity-verified restore
            restored = False
            try:
                from app.database.operations.backup import get_sqlite_backup_manager

                manager = get_sqlite_backup_manager()
                if manager is not None:
                    result = manager.restore_latest()
                    if result.restored:
                        restored = True
                        system_status.database_recovered = True
                        await reset_database_engine()
                        await init_database()
                        logger.info(
                            "[Startup] Database restored from snapshot %s",
                            result.snapshot_file,
                        )
            except Exception as restore_exc:
                logger.warning("[Startup] Snapshot restore failed: %s", restore_exc)

            # 3. Degrade to in-memory as ultimate fallback
            if not restored:
                logger.warning("[Startup] All recovery methods exhausted, degrading to in-memory mode")
                system_status.database_degraded = True
                settings.database.sqlite_path = ":memory:"
                await reset_database_engine()
                await init_database()

    from app.services.chat.compact.compression_streak import (
        register_chat_compression_streak_store,
    )

    register_chat_compression_streak_store()
    logger.info("[Startup] Compression streak store registered (Chat DB)")

    try:
        from app.platform_utils.sandbox.saas_providers_seed import (
            seed_saas_platform_providers_if_needed,
        )

        await seed_saas_platform_providers_if_needed()
    except Exception as exc:
        logger.warning("[Startup] SaaS provider seed skipped: %s", exc)

    await _register_db_pool_metrics_task()

    try:
        from myrm_agent_harness.core.features import init_features

        from app.services.features.feature_config_service import (
            load_user_overrides,
            sanitize_user_overrides,
        )
        from app.services.features.registration import register_all_features

        register_all_features()
        user_overrides = load_user_overrides()
        user_overrides = sanitize_user_overrides(user_overrides)
        feature_set = init_features(overrides=user_overrides)
        logger.info(
            "[Startup] Feature flags initialized (%d enabled)",
            len(feature_set.enabled_features()),
        )
    except Exception as e:
        logger.error("[Startup] Feature flags initialization failed: %s", e)
        raise

    try:
        from app.services.config.migration import seal_stored_configs

        await seal_stored_configs()
    except Exception as e:
        logger.warning("[Startup] Config encryption migration failed (non-critical): %s", e)

    try:
        from app.services.config.key_consolidation import (
            consolidate_split_providers_keys,
        )

        stats = await consolidate_split_providers_keys()
        if stats.get("merged") or stats.get("deleted"):
            logger.info("[Startup] Providers key consolidation complete: %s", stats)
    except Exception as e:
        logger.warning("[Startup] Providers key consolidation failed (non-critical): %s", e)

    try:
        from app.database.connection import get_session
        from app.services.integrations.retired_provider_oauth_purge import (
            purge_retired_provider_credentials,
        )

        async with get_session() as db:
            await purge_retired_provider_credentials(db)
    except Exception as e:
        logger.warning("[Startup] Retired provider OAuth credential purge failed (non-critical): %s", e)

    # Subscription access tokens are short-lived, so a model instance that outlives one renews it per request.
    try:
        from myrm_agent_harness.api.hooks import set_api_key_refresher

        from app.services.agent.provider_oauth_tokens import freshen_api_key

        set_api_key_refresher(freshen_api_key)
    except Exception as e:
        logger.error("[Startup] Subscription token refresher registration failed: %s", e)

    try:
        from app.core.infra.tls_config import apply_tls_config_from_db

        await apply_tls_config_from_db()
    except Exception as e:
        logger.debug("[Startup] TLS config from DB skipped: %s", e)

    # Privacy protection must cover model calls that have no agent run (titles, summaries, memory extraction)
    # from the first request, so the saved policy is published before any of them can happen.
    try:
        from app.core.security.privacy_policy_sync import apply_privacy_policy_from_db

        await apply_privacy_policy_from_db()
    except Exception as e:
        logger.error("[Startup] Privacy policy from saved settings failed to apply: %s", e)

    # Register Control Plane URL to Harness SSRF dynamic blocklist
    try:
        from urllib.parse import urlparse

        from myrm_agent_harness.api.security import register_blocked_hostnames

        cp_url = settings.control_plane.url.strip()
        if cp_url:
            parsed_cp = urlparse(cp_url)
            if parsed_cp.hostname:
                register_blocked_hostnames(parsed_cp.hostname)
                logger.info(
                    "[Startup] Registered control plane host '%s' to SSRF blocklist",
                    parsed_cp.hostname,
                )
    except Exception as cp_err:
        logger.warning("[Startup] Control plane SSRF registration skipped: %s", cp_err)


async def _phase_1b_parallel() -> None:
    """Phase 1b: Parallel independent tasks after DB ready."""

    async def _init_code_execution_config() -> None:
        _apply_code_execution_config()

    async def _init_checkpointer_task() -> None:
        from myrm_agent_harness.runtime.checkpointing.factory import create_checkpointer

        from app.config.deploy_mode import get_deploy_mode
        from app.config.settings import settings
        from app.platform_utils import set_checkpointer

        checkpointer, state._checkpointer_cleanup = await create_checkpointer(
            mode=settings.database.checkpointer_mode,
            sqlite_db_path=settings.database.sqlite_db_path,
            deploy_mode=get_deploy_mode().value,
        )
        set_checkpointer(checkpointer)
        logger.info("[Startup] Checkpointer initialized")

    async def _init_state_manager_task() -> None:
        from app.core.skills.state_manager_instance import init_state_manager

        init_state_manager(base_dir=".myrm/skills")
        logger.info("[Startup] SkillStateManager initialized")

    async def _init_allowlist_store_task() -> None:
        await init_allowlist_store()

    async def _init_workspace_trust_store_task() -> None:
        await init_workspace_trust_store()

    def _init_managed_approval_policy_task() -> None:
        from myrm_agent_harness.api.security import (
            configure_process_managed_approval_policy,
            load_managed_approval_policy_from_env,
        )

        configure_process_managed_approval_policy(load_managed_approval_policy_from_env())
        logger.info("[Startup] Managed approval policy initialized from env")

    async def _init_permission_logger_task() -> None:
        from app.core.skills.gates.permission_logger import start_permission_logger

        start_permission_logger()
        logger.info("[Startup] Skill permission logger started")

    async def _init_context_cleanup_task() -> None:
        from pathlib import Path

        from myrm_agent_harness.runtime.context.cleanup_task import (
            ContextCleanupScheduler,
        )
        from myrm_agent_harness.toolkits.code_execution import create_workspace_service

        workspace_svc = create_workspace_service(root_dir=Path(settings.database.harness_dir))
        sandboxes_root = workspace_svc.workspaces_root

        # ContextGuard transient spillover initial sweep
        try:
            from app.services.agent.context_guard_service import ContextGuardService

            ContextGuardService.sweep_all_workspaces(sandboxes_root)
        except Exception as cg_err:
            logger.debug("[Startup] ContextGuard initial sweep skipped: %s", cg_err)

        if sandboxes_root.exists():
            scheduler = ContextCleanupScheduler(sandboxes_root, interval_hours=24)
            scheduler.start()
            state._context_cleanup_scheduler_instance = scheduler
            logger.info("[Startup] Context cleanup task started (root: %s)", sandboxes_root)
        else:
            logger.debug(
                "[Startup] Sandboxes root not found, skip cleanup task: %s",
                sandboxes_root,
            )

    async def _init_idle_handlers_task() -> None:
        from app.core.infra.idle_handlers import register_all_idle_handlers

        register_all_idle_handlers()

    async def _init_prebuilt_skills() -> None:
        from myrm_agent_harness.toolkits.storage.factory import get_storage_provider

        from app.core.skills.prebuilt_sync import sync_prebuilt_seeds
        from app.core.skills.store.service import skills_service

        storage = get_storage_provider()
        sync_result = await sync_prebuilt_seeds(storage)
        from app.api.health.update_status import note_prebuilt_sync_result

        note_prebuilt_sync_result(sync_result.synced_count)
        if sync_result.skill_ids:
            await skills_service.user_config.ensure_prebuilt_enabled_after_sync(list(sync_result.skill_ids))

    async def _init_builtin_agents() -> None:
        from app.services.agent.builtin_specs.builtin_initializer import (
            initialize_builtin_agents,
        )

        await initialize_builtin_agents()

    async def _init_harness_bridge_task() -> None:
        from app.lifecycle.harness_bridge import setup_harness_bridge

        setup_harness_bridge()

    async def _init_security_reviewer_task() -> None:
        from myrm_agent_harness.agent.middlewares.approval.batch_processor import (
            register_security_reviewer,
        )

        from app.core.security.llm_reviewer import DynamicLLMSecurityReviewer

        try:
            reviewer = DynamicLLMSecurityReviewer(timeout_seconds=3.0)
            register_security_reviewer(reviewer)
            logger.info("[Startup] DynamicLLMSecurityReviewer initialized and registered")
        except Exception as e:
            logger.warning("[Startup] Failed to initialize DynamicLLMSecurityReviewer: %s", e)

    async def _init_vault_credentials_task() -> None:
        from app.services.security.vault_credential_service import (
            VaultCredentialService,
        )

        try:
            service = VaultCredentialService()
            await service.sync_all_to_vault()
        except Exception as e:
            logger.error("[Startup] Failed to sync Vault Credentials: %s", e)

    async def _init_wiki_vault_task() -> None:
        from app.services.wiki.vault import init_wiki_vault_at_startup

        await init_wiki_vault_at_startup()

    async def _init_context_guard_sweeper_task() -> None:
        from app.services.agent.context_guard_service import ContextGuardService

        try:
            cleaned = ContextGuardService.sweep_all_workspaces()
            logger.info("[Startup] ContextGuard initial transient sweep completed: cleaned=%d files", cleaned)
        except Exception as e:
            logger.warning("[Startup] ContextGuard transient sweep encountered error: %s", e)

    _init_managed_approval_policy_task()

    results = await asyncio.gather(
        _init_code_execution_config(),
        _init_checkpointer_task(),
        _init_state_manager_task(),
        _init_allowlist_store_task(),
        _init_workspace_trust_store_task(),
        _init_permission_logger_task(),
        _init_context_cleanup_task(),
        _init_context_guard_sweeper_task(),
        _init_idle_handlers_task(),
        _init_prebuilt_skills(),
        _init_builtin_agents(),
        _init_harness_bridge_task(),
        _init_security_reviewer_task(),
        _init_vault_credentials_task(),
        _init_wiki_vault_task(),
        return_exceptions=True,
    )

    _labels = [
        "Code execution config",
        "Checkpointer",
        "State manager",
        "Allowlist store",
        "Workspace trust store",
        "Permission logger",
        "Context cleanup",
        "ContextGuard sweep",
        "Idle handlers",
        "Prebuilt skills",
        "Built-in agents",
        "Harness event bridge",
        "Security reviewer",
        "Vault credentials",
        "Wiki vault",
    ]
    for label, result in zip(_labels, results, strict=True):
        if isinstance(result, Exception):
            logger.error("[Startup] %s initialization failed: %s", label, result)
