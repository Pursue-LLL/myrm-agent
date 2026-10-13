"""The message filter configuration holds only the switches the filter pipeline reads."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.message_filter.config import FilterConfigSchema, get_config, update_config


async def test_a_fresh_configuration_carries_no_pii_mode(db_session: AsyncSession) -> None:
    config = await get_config(db_session)

    assert config.model_dump(exclude={"id"}) == {
        "enabled": True,
        "whitelist_api_keys": [],
        "audit_enabled": True,
        "updated_by": None,
    }


async def test_an_update_round_trips_every_switch(db_session: AsyncSession) -> None:
    payload = FilterConfigSchema(enabled=False, whitelist_api_keys=["sk-allowed"], audit_enabled=False)

    updated = await update_config(payload, updated_by="admin", db=db_session)

    assert (updated.enabled, updated.whitelist_api_keys, updated.audit_enabled, updated.updated_by) == (
        False,
        ["sk-allowed"],
        False,
        "admin",
    )
    assert await get_config(db_session) == updated


def test_a_client_still_sending_pii_mode_is_tolerated() -> None:
    payload = FilterConfigSchema.model_validate({"enabled": True, "pii_mode": "block"})

    assert not hasattr(payload, "pii_mode")
