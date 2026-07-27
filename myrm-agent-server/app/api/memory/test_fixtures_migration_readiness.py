"""Local-only migration readiness Chrome E2E seed routes.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
app.services.agent.agent_service::AgentService (POS: agent list for seed scope)
app.services.memory.import_sessions::MemoryImportSessionService (POS: readiness recheck facts)

[OUTPUT]
seed_migration_readiness_fixture: post-import readiness batch for Chrome E2E

[POS]
Memory API local test fixture for MigrationWizard readiness Chrome E2E seeds.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode
from app.platform_utils import get_session_factory
from app.services.agent.agent_service import AgentService
from app.services.memory.import_sessions import (
    ImportReadinessRecheckFacts,
    MemoryImportSessionService,
)

router = APIRouter()

_VARIANTS = frozenset({"mcp_warning", "provider_critical"})


class _SeedFixtureMemoryManager:
    """Minimal in-process manager for E2E seed — no embedding/Qdrant required."""

    def __init__(self) -> None:
        self._memory_ids_by_type: dict[str, list[str]] = {}

    async def import_memories(
        self,
        data: dict[str, list[dict[str, object]]],
        *,
        skip_duplicates: bool = True,
    ) -> dict[str, int]:
        _ = skip_duplicates
        counts: dict[str, int] = {}
        for memory_type, entries in data.items():
            ids = [f"{memory_type}-{index}" for index, _entry in enumerate(entries)]
            self._memory_ids_by_type[memory_type] = ids
            counts[memory_type] = len(ids)
        return counts

    async def list_memory_refs_by_metadata(
        self,
        metadata_key: str,
        metadata_value: str,
    ) -> dict[str, list[dict[str, str]]]:
        _ = metadata_key
        return {
            memory_type: [
                {
                    "id": memory_id,
                    "import_item_id": f"{metadata_value}:{memory_type}:{index}",
                }
                for index, memory_id in enumerate(memory_ids)
            ]
            for memory_type, memory_ids in self._memory_ids_by_type.items()
            if memory_ids
        }


@router.post("/test/seed-migration-readiness-fixture", include_in_schema=False)
async def seed_migration_readiness_fixture(
    variant: str = "mcp_warning",
) -> dict[str, str]:
    """Local dev/test only: seed post-import readiness batch for Chrome E2E."""

    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    normalized = variant.strip().lower()
    if normalized not in _VARIANTS:
        raise HTTPException(status_code=400, detail=f"Unsupported variant: {variant}")

    session_factory = get_session_factory()
    async with session_factory() as db:
        agents, _total = await AgentService.get_agent_list(page=1, page_size=1)
        if not agents:
            raise HTTPException(
                status_code=503,
                detail="No agent available for migration readiness seed.",
            )
        target_agent_id = str(agents[0].id)

        service = MemoryImportSessionService(db)
        manager = _SeedFixtureMemoryManager()
        payload = {
            "data": {
                "semantic": [
                    {
                        "content": "Migration readiness Chrome E2E seed.",
                        "metadata": {"source": "e2e_seed"},
                    }
                ]
            }
        }
        dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(
            payload,
            "native_json",
        )
        confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)
        await service.save_post_import_diagnostic(
            import_batch_id=confirm.import_batch_id,
            diagnostic_run_id="diag-ready",
            diagnostic_status="ready",
            failed_count=0,
        )

        if normalized == "provider_critical":
            await service.save_post_import_readiness(
                import_batch_id=confirm.import_batch_id,
                readiness_status="critical",
                readiness_issues=[
                    {
                        "code": "providers_not_configured",
                        "severity": "critical",
                        "params": {},
                        "settings_path": "/settings/models",
                    }
                ],
                recheck_facts=ImportReadinessRecheckFacts(
                    source_has_api_keys=True,
                    diagnostic_status="ready",
                    diagnostic_failed_count=0,
                    mcp_config_count=0,
                    workspace_rules_skipped=0,
                ),
            )
            readiness_status = "critical"
        else:
            await service.save_post_import_readiness(
                import_batch_id=confirm.import_batch_id,
                readiness_status="warning",
                readiness_issues=[
                    {
                        "code": "mcp_servers_imported_disabled",
                        "severity": "warning",
                        "params": {"count": 2},
                        "settings_path": "/settings/mcp",
                    }
                ],
                recheck_facts=ImportReadinessRecheckFacts(
                    source_has_api_keys=False,
                    diagnostic_status="ready",
                    diagnostic_failed_count=0,
                    mcp_config_count=2,
                    workspace_rules_skipped=0,
                ),
            )
            readiness_status = "warning"

    return {
        "import_batch_id": confirm.import_batch_id,
        "target_agent_id": target_agent_id,
        "readiness_status": readiness_status,
        "variant": normalized,
        "chat_ui_path": f"/?agentId={target_agent_id}",
        "settings_path": (
            "/settings/mcp" if normalized == "mcp_warning" else "/settings/models"
        ),
    }
