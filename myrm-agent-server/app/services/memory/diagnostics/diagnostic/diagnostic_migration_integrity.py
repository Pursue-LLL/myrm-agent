"""Memory Doctor migration integrity check.

[INPUT]
app.database.migrations::MIGRATION_STATEMENTS (POS: 内置迁移清单)
sqlalchemy.ext.asyncio::AsyncSession (POS: 本地数据库会话)

[OUTPUT]
inspect_migration_integrity: compares applied migration checksums with the current manifest.
run_migration_integrity_probe: the same check as a timed diagnostic probe.

[POS]
单用户记忆迁移完整性检查。只读 `_schema_migrations` 状态表，让 schema drift 在启动或导入回滚失败前可见。
"""

from __future__ import annotations

import hashlib
from time import perf_counter

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.memory.command_center import MemoryCommandDiagnosticProbeResult, MemoryCommandDoctorCheck

from .diagnostic_probe_results import DiagnosticStatus, doctor_check_to_probe


async def run_migration_integrity_probe(db: AsyncSession) -> MemoryCommandDiagnosticProbeResult:
    started = perf_counter()
    check = await inspect_migration_integrity(db)
    return doctor_check_to_probe(check, duration_ms=round((perf_counter() - started) * 1000, 2))


async def inspect_migration_integrity(db: AsyncSession) -> MemoryCommandDoctorCheck:
    try:
        from app.database.migrations import MIGRATION_STATEMENTS

        expected = {index: hashlib.sha256(sql.encode("utf-8")).hexdigest() for index, sql in enumerate(MIGRATION_STATEMENTS)}
        result = await db.execute(text("SELECT version, checksum FROM _schema_migrations"))
        applied: dict[int, str] = {int(row[0]): str(row[1]) for row in result.fetchall()}
    except Exception as exc:
        return MemoryCommandDoctorCheck(
            id="migration_integrity",
            category="migration",
            label="Migration integrity",
            status="critical",
            evidence=f"Migration state inspection failed: {type(exc).__name__}.",
            impact="The local schema migration ledger cannot be trusted until the database state table is readable.",
            next_action="Review the SQLite database state and rerun diagnostics.",
            safe_to_retry=True,
            repair_actions=["review_storage_config", "run_diagnostics"],
        )

    drifted = [
        version
        for version, checksum in applied.items()
        if version in expected and not checksum.startswith("baselined:") and checksum != expected[version]
    ]
    pending = [version for version in expected if version not in applied]
    unknown = [version for version in applied if version not in expected]
    if drifted:
        status: DiagnosticStatus = "critical"
        next_action = "Do not modify historical migrations; create a forward repair migration or rebuild an isolated sandbox."
        repair_actions = ["review_storage_config"]
    elif pending or unknown:
        status = "warning"
        next_action = "Restart through the normal app lifecycle so pending migrations can apply, then rerun diagnostics."
        repair_actions = ["run_diagnostics"]
    else:
        status = "ready"
        next_action = "No action required."
        repair_actions = []
    evidence = (
        f"Migration ledger checked {len(applied)} applied version(s); "
        f"drifted={len(drifted)}, pending={len(pending)}, unknown={len(unknown)}."
    )
    return MemoryCommandDoctorCheck(
        id="migration_integrity",
        category="migration",
        label="Migration integrity",
        status=status,
        evidence=evidence,
        impact="Schema integrity protects startup, rollback, import review storage, and command-center audit durability.",
        next_action=next_action,
        safe_to_retry=True,
        repair_actions=repair_actions,
    )
