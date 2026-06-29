"""Context bundle service.

[INPUT]
- app.services.context.context_assembly::ContextAssemblyService (POS: context assembly)
- myrm_agent_harness.toolkits.context_bundle (POS: context bundle toolkit)

[OUTPUT]
- ContextBundleService: bundle health, migration dry-run/apply

[POS]
Server-side ContextBundle orchestration. Wraps Harness facade without duplicating memory logic.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.context_bundle import (
    ContextBundleFacade,
    ContextScene,
    apply_migration,
    run_migration_dry_run,
)
from myrm_agent_harness.toolkits.context_bundle.health import (
    HealthProbe,
    MemorySceneHealthBackend,
    StaticSceneHealthBackend,
)

try:
    from myrm_agent_harness.toolkits.context_bundle.health import WorkspaceSceneHealthBackend
except ImportError:
    from myrm_agent_harness.toolkits.context_bundle.health import (
        LocalFileSearchSceneHealthBackend as WorkspaceSceneHealthBackend,
    )

from app.config.deploy_mode import get_deploy_mode, get_storage_mode
from app.config.settings import settings
from app.schemas.context.bundle import (
    ContextBundleHealthResponse,
    ContextBundleMigrationResponse,
    ContextBundleSceneHealth,
)
from app.services.context.context_assembly import ContextAssemblyService


class ContextBundleService:
    """Build context bundle health and apply non-destructive layout migrations."""

    def _facade_with_probes(self) -> ContextBundleFacade:
        facade = ContextAssemblyService.build_facade(ensure_layout=False)
        registry = facade.index()
        registry.register(MemorySceneHealthBackend(facade.memory_path()))
        registry.register(WorkspaceSceneHealthBackend(_make_workspace_health_probe(facade)))
        registry.register(StaticSceneHealthBackend(ContextScene.OFFLOAD, _path_writable_status(facade.offload_root())))
        registry.register(StaticSceneHealthBackend(ContextScene.ARCHIVE, _path_writable_status(facade.archive_path())))
        return facade

    async def get_health(self) -> ContextBundleHealthResponse:
        facade = self._facade_with_probes()
        health = await facade.health()
        migration = run_migration_dry_run(settings.database.state_dir, spec=facade.spec)
        scenes = [
            ContextBundleSceneHealth(
                scene=scene,
                path=path,
                index_status=_normalize_index_status(health.index_status.get(scene, "missing")),
            )
            for scene, path in health.scene_paths.items()
        ]
        return ContextBundleHealthResponse(
            bundle_id=health.bundle_id,
            schema_version=health.schema_version,
            volume_layout_version=health.volume_layout_version,
            state_dir=health.state_dir,
            memory_base_path=str(facade.memory_path()),
            harness_dir=str(facade.harness_path()),
            writable=health.writable,
            manifest_exists=health.manifest_exists,
            deploy_mode=get_deploy_mode(),
            storage_mode=get_storage_mode(),
            scenes=scenes,
            migration_actions_pending=len(migration.actions),
            warnings=list(migration.warnings),
        )

    def run_migration_dry_run(self) -> ContextBundleMigrationResponse:
        facade = ContextAssemblyService.build_facade(ensure_layout=False)
        report = run_migration_dry_run(settings.database.state_dir, spec=facade.spec)
        return ContextBundleMigrationResponse(
            ok=report.ok,
            bundle_id=report.bundle_id,
            schema_version=report.schema_version,
            writable=report.writable,
            manifest_exists=report.manifest_exists,
            actions=[action.description for action in report.actions],
            warnings=list(report.warnings),
        )

    def apply_migration(self) -> ContextBundleMigrationResponse:
        facade = ContextAssemblyService.build_facade(ensure_layout=False)
        apply_migration(settings.database.state_dir, spec=facade.spec)
        return self.run_migration_dry_run()


def _make_workspace_health_probe(facade: ContextBundleFacade) -> HealthProbe:
    harness_path = facade.harness_path()

    async def probe() -> str:
        path_status = _path_writable_status(harness_path)
        if path_status != "ready":
            return path_status
        from shutil import which

        return "ready" if which("rg") is not None else "degraded"

    return probe


def _path_writable_status(path: object) -> str:
    import os
    from pathlib import Path

    target = Path(str(path))
    check = target if target.exists() else target.parent
    if check.exists() and os.access(check, os.W_OK):
        return "ready"
    return "critical"


def _normalize_index_status(value: str) -> str:
    if value in {"ready", "degraded", "missing", "critical"}:
        return "degraded" if value == "critical" else value
    return "missing"
