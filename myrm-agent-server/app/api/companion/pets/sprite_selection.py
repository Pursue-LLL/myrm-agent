"""Companion sprite selection — which installed pet the companion config points at.

[INPUT]
app.services.config.service::config_service (POS: 配置服务，`companion_config` 的读写)
app.schemas.config::ConfigRecord (POS: 配置记录，含 value 与 version)

[OUTPUT]
persist_sprite_selection: 把宠物写成伴侣配置里的精灵
clear_sprite_selection_if_matches: 卸载的正是当前精灵时把它清掉

[POS]
伴侣配置里的精灵选择。装宠物、迁移旧配置时写入，卸载当前宠物时清除；路由层只调用，不碰配置字典。
"""

from __future__ import annotations

from pathlib import Path

from app.schemas.config import ConfigRecord


async def persist_sprite_selection(
    *,
    pet_slug: str,
    content_sha256: str,
    display_name: str | None,
    device_id: str = "default_device",
) -> ConfigRecord:
    """Point the companion config at an installed pet, keeping its other fields."""
    from app.services.config.service import config_service

    record = await config_service.get("companion_config")
    base: dict[str, object] = dict(record.value) if record and isinstance(record.value, dict) else {}
    base["sprite"] = {
        "pet_slug": pet_slug,
        "content_sha256": content_sha256,
        "display_name": display_name,
    }
    return await config_service.set(
        config_key="companion_config",
        value=base,
        device_id=device_id,
    )


def _normalize_pet_slug(slug: str) -> str:
    segment = Path(str(slug).strip()).name
    if segment in ("", ".", ".."):
        return ""
    return segment


async def clear_sprite_selection_if_matches(
    pet_slug: str,
    *,
    device_id: str = "default_device",
) -> None:
    """Clear persisted sprite when uninstalling the active pet slug."""
    from app.services.config.service import config_service

    normalized = _normalize_pet_slug(pet_slug)
    if not normalized:
        return

    record = await config_service.get("companion_config")
    if not record or not isinstance(record.value, dict):
        return

    sprite_raw = record.value.get("sprite")
    if not isinstance(sprite_raw, dict):
        return

    config_slug = sprite_raw.get("pet_slug")
    if not isinstance(config_slug, str):
        return
    if _normalize_pet_slug(config_slug) != normalized:
        return

    base = dict(record.value)
    base["sprite"] = None
    await config_service.set(
        config_key="companion_config",
        value=base,
        device_id=device_id,
    )
