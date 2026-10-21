"""Companion pet health diagnostics (read-only).

[INPUT]
- Feature gate, companion_config, on-disk pet store (POS: business companion layer)

[OUTPUT]
- CompanionDoctorReport: structured pass/warn/fail checks for GUI health panel

[POS]
Server-side SSOT for Companion sprite install/render troubleshooting; no feature gate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.services.companion.pet_atlas import (
    AtlasReport,
    FormatTier,
    analyze_spritesheet,
)
from app.services.companion.pet_store import list_installed_pets, load_pet

logger = logging.getLogger(__name__)


class CheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    id: str
    status: CheckStatus
    message: str
    fix_action: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "id": self.id,
            "status": self.status.value,
            "message": self.message,
            "fixAction": self.fix_action,
        }


@dataclass(frozen=True, slots=True)
class CompanionDoctorReport:
    ready: bool
    checks: tuple[DoctorCheck, ...]
    active_slug: str | None
    installed_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "checks": [check.to_dict() for check in self.checks],
            "activeSlug": self.active_slug,
            "installedCount": self.installed_count,
        }


def _read_sprite_config(raw: dict[str, object]) -> tuple[str | None, str | None]:
    sprite_raw = raw.get("sprite")
    if not isinstance(sprite_raw, dict):
        return None, None
    slug_val = sprite_raw.get("pet_slug")
    sha_val = sprite_raw.get("content_sha256")
    slug = slug_val.strip() if isinstance(slug_val, str) and slug_val.strip() else None
    sha = sha_val.strip() if isinstance(sha_val, str) and sha_val.strip() else None
    return slug, sha


def _load_atlas_report(meta: dict[str, object], *, rescan_path: str | None) -> AtlasReport | None:
    atlas_raw = meta.get("atlasReport")
    if isinstance(atlas_raw, dict) and not rescan_path:
        parsed = AtlasReport.from_dict(atlas_raw)
        if parsed is not None:
            return parsed
    if not rescan_path:
        return None
    try:
        from pathlib import Path

        return analyze_spritesheet(Path(rescan_path))
    except ValueError as exc:
        logger.debug("Atlas rescan failed for %s: %s", rescan_path, exc)
        return None


async def run_companion_doctor(*, rescan: bool = False) -> CompanionDoctorReport:
    """Run read-only companion sprite diagnostics."""
    from myrm_agent_harness.core.features import get_features

    from app.services.config.service import config_service

    checks: list[DoctorCheck] = []

    feature_enabled = get_features().enabled("companion_mode")
    if feature_enabled:
        checks.append(
            DoctorCheck(
                id="feature_gate.companion_mode",
                status=CheckStatus.PASS,
                message="Companion feature is enabled.",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                id="feature_gate.companion_mode",
                status=CheckStatus.FAIL,
                message="Companion feature is disabled. Re-enable it in Settings.",
                fix_action="open_experimental_companion",
            )
        )

    record = await config_service.get("companion_config")
    config_val: dict[str, object] = dict(record.value) if record and isinstance(record.value, dict) else {}
    config_slug, config_sha = _read_sprite_config(config_val)

    if config_slug:
        checks.append(
            DoctorCheck(
                id="config.sprite.slug",
                status=CheckStatus.PASS,
                message=f"Active pet slug is set to '{config_slug}'.",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                id="config.sprite.slug",
                status=CheckStatus.FAIL,
                message="No active pet slug in companion config.",
                fix_action="open_pet_gallery",
            )
        )

    installed = list_installed_pets()
    installed_slugs = {pet.slug for pet in installed}

    if not installed:
        checks.append(
            DoctorCheck(
                id="disk.installed_pets",
                status=CheckStatus.FAIL,
                message="No pets installed on disk.",
                fix_action="open_pet_gallery",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                id="disk.installed_pets",
                status=CheckStatus.PASS,
                message=f"{len(installed)} pet(s) installed ({', '.join(p.slug for p in installed)}).",
            )
        )

    active_pet = load_pet(config_slug) if config_slug else None
    rescan_path = str(active_pet.spritesheet) if rescan and active_pet and active_pet.exists else None

    if config_slug and config_slug not in installed_slugs:
        checks.append(
            DoctorCheck(
                id="disk.active_pet_files",
                status=CheckStatus.FAIL,
                message=f"Configured pet '{config_slug}' is not installed on disk.",
                fix_action="open_pet_gallery",
            )
        )
    elif active_pet is None or not active_pet.exists:
        checks.append(
            DoctorCheck(
                id="disk.active_pet_files",
                status=CheckStatus.FAIL,
                message="Active pet spritesheet file is missing.",
                fix_action="open_pet_gallery",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                id="disk.active_pet_files",
                status=CheckStatus.PASS,
                message=f"Spritesheet file exists for '{active_pet.slug}'.",
            )
        )

        meta: dict[str, object] = {}
        pet_json = active_pet.directory / "pet.json"
        if pet_json.is_file():
            try:
                import json

                loaded = json.loads(pet_json.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    meta = loaded
            except (OSError, ValueError) as exc:
                logger.debug("Unreadable pet.json during doctor: %s", exc)

        atlas = _load_atlas_report(meta, rescan_path=rescan_path)
        if atlas is None and rescan:
            try:
                atlas = analyze_spritesheet(active_pet.spritesheet)
            except ValueError as exc:
                checks.append(
                    DoctorCheck(
                        id="atlas.format",
                        status=CheckStatus.FAIL,
                        message=str(exc),
                        fix_action="open_pet_gallery",
                    )
                )
                atlas = None

        if atlas is not None:
            if rescan and config_slug:
                from app.services.companion.pet_store import persist_atlas_report

                persist_atlas_report(config_slug, atlas)

            if atlas.format_tier == FormatTier.OK:
                atlas_status = CheckStatus.PASS
            elif atlas.format_tier == FormatTier.WARN:
                atlas_status = CheckStatus.WARN
            else:
                atlas_status = CheckStatus.FAIL
            checks.append(
                DoctorCheck(
                    id="atlas.format",
                    status=atlas_status,
                    message=atlas.message,
                    fix_action=(None if atlas_status == CheckStatus.PASS else "open_pet_gallery"),
                )
            )
        elif active_pet.exists:
            checks.append(
                DoctorCheck(
                    id="atlas.format",
                    status=CheckStatus.WARN,
                    message="Atlas format has not been validated yet. Re-install or run rescan.",
                    fix_action="doctor_rescan",
                )
            )

        disk_sha = active_pet.content_sha256
        if config_sha and disk_sha and config_sha != disk_sha:
            checks.append(
                DoctorCheck(
                    id="config.sha256_match",
                    status=CheckStatus.WARN,
                    message="Configured SHA256 does not match the on-disk spritesheet.",
                    fix_action="open_pet_gallery",
                )
            )
        elif config_sha:
            checks.append(
                DoctorCheck(
                    id="config.sha256_match",
                    status=CheckStatus.PASS,
                    message="Configured SHA256 matches the on-disk spritesheet.",
                )
            )

        if not active_pet.spritesheet.is_file():
            checks.append(
                DoctorCheck(
                    id="serve.file_readable",
                    status=CheckStatus.FAIL,
                    message="Spritesheet path is not readable.",
                    fix_action="open_pet_gallery",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    id="serve.file_readable",
                    status=CheckStatus.PASS,
                    message="Spritesheet file is readable for local serve.",
                )
            )

    blocking = any(
        check.status == CheckStatus.FAIL
        for check in checks
        if check.id
        in {
            "feature_gate.companion_mode",
            "config.sprite.slug",
            "disk.installed_pets",
            "disk.active_pet_files",
            "atlas.format",
            "serve.file_readable",
        }
    )
    ready = feature_enabled and not blocking and config_slug is not None

    return CompanionDoctorReport(
        ready=ready,
        checks=tuple(checks),
        active_slug=config_slug,
        installed_count=len(installed),
    )


__all__ = [
    "CheckStatus",
    "CompanionDoctorReport",
    "DoctorCheck",
    "run_companion_doctor",
]
