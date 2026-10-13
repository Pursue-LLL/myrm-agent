"""Market install/update with Skill Change Contract snapshots.

[INPUT]
- app.core.skills.replace::create_replace_snapshot (POS: batch snapshot)
- app.core.skills.marketplace.market_service::market_service (POS: quarantine install)

[OUTPUT]
- market_install_with_replace_snapshot / market_install_from_url_with_replace_snapshot

[POS]
Shared by discovery /install, /install-from-url, and autoupdate update_skill.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult

from app.core.skills.models import Skill
from app.core.skills.replace import (
    SkillReplaceBlockedError,
    assert_replace_allowed,
    create_replace_snapshot,
    install_result_from_blocked,
)

logger = logging.getLogger(__name__)


async def _resolve_installed(skill_id: str, skill_name: str) -> Skill | None:
    from app.core.skills.store.service import skills_service

    installed = await skills_service.get_skill(skill_id)
    if installed is not None:
        return installed
    by_name = await skills_service.list_skills()
    return next((s for s in by_name if s.name == skill_name), None)


async def _snapshot_if_installed(
    installed: Skill | None,
    *,
    batch_kind: str,
) -> tuple[str | None, bool, frozenset[str]]:
    if installed is None:
        return None, False, frozenset()
    try:
        await assert_replace_allowed(installed)
        batch_id, truncated, snapshotted_paths = await create_replace_snapshot(
            installed.id,
            installed.name,
            batch_kind=batch_kind,
        )
        return batch_id, truncated, snapshotted_paths
    except SkillReplaceBlockedError:
        raise
    except Exception as exc:
        logger.error("Replace snapshot failed for %s: %s", installed.id, exc)
        raise


async def market_install_with_replace_snapshot(
    skill_id: str,
    source: str,
    *,
    skill_name: str = "",
    allow_downgrade: bool = False,
    batch_kind: str = "market-replace",
) -> tuple[SkillInstallResult, str | None, bool]:
    from app.core.skills.marketplace.market_service import market_service

    installed = await _resolve_installed(skill_id, skill_name or skill_id)
    batch_id: str | None = None
    snapshot_truncated = False
    snapshotted_paths: frozenset[str] = frozenset()
    if installed is not None:
        try:
            batch_id, snapshot_truncated, snapshotted_paths = await _snapshot_if_installed(installed, batch_kind=batch_kind)
        except SkillReplaceBlockedError as exc:
            return (
                install_result_from_blocked(exc, skill_name=installed.name, skill_id=installed.id),
                None,
                False,
            )
        except Exception:
            return (
                SkillInstallResult(
                    success=False,
                    skill_name=installed.name,
                    skill_id=installed.id,
                    error="Failed to snapshot skill before replace.",
                    error_code="snapshot_failed",
                ),
                None,
                False,
            )

    result = await market_service.install(
        skill_id=skill_id,
        source=source,
        allow_downgrade=allow_downgrade,
    )

    if result.success and batch_id:
        target_id = result.skill_id or (installed.id if installed else "")
        if target_id:
            from app.core.skills.replace.finalize import finalize_market_replace_success

            snapshot_truncated = await finalize_market_replace_success(
                target_id,
                batch_id,
                snapshot_truncated=snapshot_truncated,
                snapshotted_paths=snapshotted_paths,
            )

    return result, batch_id, snapshot_truncated


async def market_install_from_url_with_replace_snapshot(
    url: str,
    *,
    allow_downgrade: bool = False,
    batch_kind: str = "market-replace",
) -> tuple[SkillInstallResult, str | None, bool]:
    from app.core.skills.marketplace.market_service import market_service

    installed: Skill | None = None
    try:
        analyzed = await market_service.analyze_url(url)
        for item in analyzed:
            if not isinstance(item, dict):
                continue
            if not item.get("is_installed"):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            installed = await _resolve_installed(name, name)
            if installed is not None:
                break
    except Exception as exc:
        logger.debug("URL analyze before replace snapshot skipped: %s", exc)

    batch_id: str | None = None
    snapshot_truncated = False
    snapshotted_paths: frozenset[str] = frozenset()
    if installed is not None:
        try:
            batch_id, snapshot_truncated, snapshotted_paths = await _snapshot_if_installed(installed, batch_kind=batch_kind)
        except SkillReplaceBlockedError as exc:
            return (
                install_result_from_blocked(exc, skill_name=installed.name, skill_id=installed.id),
                None,
                False,
            )
        except Exception:
            return (
                SkillInstallResult(
                    success=False,
                    skill_name=installed.name,
                    skill_id=installed.id,
                    error="Failed to snapshot skill before replace.",
                    error_code="snapshot_failed",
                ),
                None,
                False,
            )

    result = await market_service.install_from_url(url, allow_downgrade=allow_downgrade)

    if result.success and batch_id:
        target_id = result.skill_id or (installed.id if installed else "")
        if target_id:
            from app.core.skills.replace.finalize import finalize_market_replace_success

            snapshot_truncated = await finalize_market_replace_success(
                target_id,
                batch_id,
                snapshot_truncated=snapshot_truncated,
                snapshotted_paths=snapshotted_paths,
            )

    return result, batch_id, snapshot_truncated
