"""Post-success hooks for market replace (honesty + undo pointer).

[INPUT]
- snapshot_honesty::merge / persist (POS: truncated signal)
- state::record_successful_replace via service (POS: last_replace_batch_id)

[OUTPUT]
- finalize_market_replace_success: merged snapshot_truncated for API responses

[POS]
Single orchestration step after successful install-overwrite.
"""

from __future__ import annotations

from app.core.skills.replace.service import record_successful_replace
from app.core.skills.replace.snapshot_honesty import (
    merge_snapshot_honesty_after_install,
    persist_replace_snapshot_truncated_flag,
)


async def finalize_market_replace_success(
    target_id: str,
    batch_id: str,
    *,
    snapshot_truncated: bool,
    snapshotted_paths: frozenset[str],
) -> bool:
    await record_successful_replace(target_id, batch_id)
    merged = await merge_snapshot_honesty_after_install(
        target_id,
        snapshot_truncated=snapshot_truncated,
        snapshotted_paths=snapshotted_paths,
        batch_id=batch_id,
        install_success=True,
    )
    await persist_replace_snapshot_truncated_flag(
        batch_id,
        target_id,
        snapshot_truncated=merged,
    )
    return merged
