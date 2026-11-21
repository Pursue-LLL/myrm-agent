"""Hosting targets CRUD stored in UserConfig.

[POS] User-managed deploy targets (Vercel, webhook).

[INPUT]
- sqlalchemy (POS: async DB session for UserConfig JSON blobs)
- app.services.config.encryption::HOSTING_TARGET_CREDENTIALS_PREFIX (POS: key family of the per-target credentials rows)

[OUTPUT]
- list/create/update/delete hosting targets with legacy Vercel ID normalization; deleting a target removes its credentials row;
  a stored target whose provider is not supported is skipped on read and leaves storage with the next write
- credential_config_key: the config row that holds one target's credentials
"""

from __future__ import annotations

import json
import uuid
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.database.models.config import UserConfig
from app.services.config.encryption import HOSTING_TARGET_CREDENTIALS_PREFIX
from app.services.hosting.types import HostingTarget, is_provider_type

HOSTING_TARGETS_KEY = "hostingTargets"
LEGACY_VERCEL_TARGET_ID = "legacy-vercel-default"


def credential_config_key(target_id: str) -> str:
    """The config row that holds the credentials of one target."""
    return f"{HOSTING_TARGET_CREDENTIALS_PREFIX}{target_id}"


def _parse_targets(raw: object) -> list[HostingTarget]:
    if not isinstance(raw, list):
        return []
    targets: list[HostingTarget] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        target_id = item.get("id")
        name = item.get("name")
        provider_type = item.get("provider_type")
        if not isinstance(target_id, str) or not isinstance(name, str) or not isinstance(provider_type, str):
            continue
        if not is_provider_type(provider_type):
            continue
        config_raw = item.get("config")
        config = {str(k): str(v) for k, v in config_raw.items()} if isinstance(config_raw, dict) else {}
        targets.append(
            HostingTarget(
                id=target_id,
                name=name,
                provider_type=provider_type,
                config=config,
                is_default=bool(item.get("is_default")),
            )
        )
    return targets


def _serialize_targets(targets: list[HostingTarget]) -> list[dict[str, object]]:
    return [
        {
            "id": t.id,
            "name": t.name,
            "provider_type": t.provider_type,
            "config": t.config,
            "is_default": t.is_default,
        }
        for t in targets
    ]


async def _load_targets_row(db: AsyncSession) -> UserConfig | None:
    return (await db.execute(select(UserConfig).where(UserConfig.config_key == HOSTING_TARGETS_KEY))).scalars().first()


async def list_hosting_targets(db: AsyncSession) -> list[HostingTarget]:
    row = await _load_targets_row(db)
    if not row:
        return []
    value = row.config_value
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return _parse_targets(value)


async def _stage_targets(db: AsyncSession, targets: list[HostingTarget]) -> None:
    """Write the targets row into the session without committing, so a caller can add related changes first.

    The row holds no secret (each target's credentials live in their own sealed row), so it is stored as plain
    JSON. The column is annotated for dict values while this row's value is an array, hence the cast.
    """
    payload = cast("dict[str, object]", _serialize_targets(targets))
    row = await _load_targets_row(db)
    if row:
        row.config_value = payload
        row.is_encrypted = False
        flag_modified(row, "config_value")
    else:
        db.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key=HOSTING_TARGETS_KEY,
                config_value=payload,
                version="1.0.0",
                last_device_id="webui",
                is_encrypted=False,
            )
        )


async def save_hosting_targets(db: AsyncSession, targets: list[HostingTarget]) -> None:
    await _stage_targets(db, targets)
    await db.commit()


async def get_hosting_target(db: AsyncSession, target_id: str) -> HostingTarget | None:
    for target in await list_hosting_targets(db):
        if target.id == target_id:
            return target
    return None


async def upsert_hosting_target(db: AsyncSession, target: HostingTarget) -> HostingTarget:
    targets = await list_hosting_targets(db)
    replaced = False
    updated: list[HostingTarget] = []
    for existing in targets:
        if existing.id == target.id:
            updated.append(target)
            replaced = True
        else:
            updated.append(
                HostingTarget(
                    id=existing.id,
                    name=existing.name,
                    provider_type=existing.provider_type,
                    config=existing.config,
                    is_default=False if target.is_default else existing.is_default,
                )
            )
    if not replaced:
        updated.append(target)
    if target.is_default:
        updated = [
            HostingTarget(
                id=t.id,
                name=t.name,
                provider_type=t.provider_type,
                config=t.config,
                is_default=t.id == target.id,
            )
            for t in updated
        ]
    await save_hosting_targets(db, updated)
    return target


async def delete_hosting_target(db: AsyncSession, target_id: str) -> bool:
    """Delete a target and its credentials row in one transaction, so no secret outlives the target it belongs to."""
    targets = await list_hosting_targets(db)
    remaining = [t for t in targets if t.id != target_id]
    if len(remaining) == len(targets):
        return False
    if remaining and not any(t.is_default for t in remaining):
        remaining[0] = HostingTarget(
            id=remaining[0].id,
            name=remaining[0].name,
            provider_type=remaining[0].provider_type,
            config=remaining[0].config,
            is_default=True,
        )
    await _stage_targets(db, remaining)
    await db.execute(delete(UserConfig).where(UserConfig.config_key == credential_config_key(target_id)))
    await db.commit()
    return True


async def get_default_hosting_target(db: AsyncSession) -> HostingTarget | None:
    targets = await list_hosting_targets(db)
    if not targets:
        return None
    for target in targets:
        if target.is_default:
            return target
    return targets[0]


async def set_default_hosting_target(db: AsyncSession, target_id: str) -> HostingTarget:
    targets = await list_hosting_targets(db)
    selected = next((t for t in targets if t.id == target_id), None)
    if selected is None:
        raise ValueError("Hosting target not found.")
    updated = [
        HostingTarget(
            id=t.id,
            name=t.name,
            provider_type=t.provider_type,
            config=t.config,
            is_default=t.id == target_id,
        )
        for t in targets
    ]
    await save_hosting_targets(db, updated)
    return next(t for t in updated if t.id == target_id)
