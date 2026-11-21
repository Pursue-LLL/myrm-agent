"""Unit tests for hosting targets CRUD."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.config import UserConfig
from app.services.hosting.credentials import load_credentials_row, load_target_credentials, save_target_credentials
from app.services.hosting.targets import (
    HOSTING_TARGETS_KEY,
    delete_hosting_target,
    get_default_hosting_target,
    get_hosting_target,
    list_hosting_targets,
    save_hosting_targets,
    set_default_hosting_target,
    upsert_hosting_target,
)
from app.services.hosting.types import HostingTarget


@pytest.mark.asyncio
async def test_save_and_list_hosting_targets(db_session: AsyncSession) -> None:
    targets = [
        HostingTarget(id="t1", name="Vercel", provider_type="vercel", config={}, is_default=True),
        HostingTarget(
            id="t2",
            name="Webhook",
            provider_type="http_webhook",
            config={"webhook_url": "https://example.com/hook"},
            is_default=False,
        ),
    ]
    await save_hosting_targets(db_session, targets)
    loaded = await list_hosting_targets(db_session)
    assert len(loaded) == 2
    assert await get_hosting_target(db_session, "t2") is not None


@pytest.mark.asyncio
async def test_upsert_hosting_target_clears_other_defaults(db_session: AsyncSession) -> None:
    await save_hosting_targets(
        db_session,
        [HostingTarget(id="a", name="A", provider_type="vercel", config={}, is_default=True)],
    )
    await upsert_hosting_target(
        db_session,
        HostingTarget(id="b", name="B", provider_type="http_webhook", config={}, is_default=True),
    )
    loaded = await list_hosting_targets(db_session)
    defaults = [t for t in loaded if t.is_default]
    assert len(defaults) == 1
    assert defaults[0].id == "b"


@pytest.mark.asyncio
async def test_delete_hosting_target_promotes_default(db_session: AsyncSession) -> None:
    await save_hosting_targets(
        db_session,
        [
            HostingTarget(id="keep", name="Keep", provider_type="vercel", config={}, is_default=True),
            HostingTarget(id="drop", name="Drop", provider_type="vercel", config={}, is_default=False),
        ],
    )
    assert await delete_hosting_target(db_session, "drop") is True
    remaining = await list_hosting_targets(db_session)
    assert len(remaining) == 1
    assert remaining[0].is_default is True


@pytest.mark.asyncio
async def test_delete_hosting_target_removes_its_credentials_row(db_session: AsyncSession) -> None:
    await save_hosting_targets(
        db_session,
        [
            HostingTarget(id="keep", name="Keep", provider_type="vercel", config={}, is_default=True),
            HostingTarget(id="drop", name="Drop", provider_type="vercel", config={}, is_default=False),
        ],
    )
    await save_target_credentials(db_session, "keep", {"token": "keep-secret"})
    await save_target_credentials(db_session, "drop", {"token": "drop-secret"})

    assert await delete_hosting_target(db_session, "drop") is True

    assert await load_credentials_row(db_session, "drop") is None
    assert await load_target_credentials(db_session, "keep") == {"token": "keep-secret"}


@pytest.mark.asyncio
async def test_delete_missing_target_returns_false(db_session: AsyncSession) -> None:
    assert await delete_hosting_target(db_session, "missing") is False


@pytest.mark.asyncio
async def test_set_default_hosting_target(db_session: AsyncSession) -> None:
    await save_hosting_targets(
        db_session,
        [
            HostingTarget(id="x", name="X", provider_type="vercel", config={}, is_default=True),
            HostingTarget(id="y", name="Y", provider_type="vercel", config={}, is_default=False),
        ],
    )
    updated = await set_default_hosting_target(db_session, "y")
    assert updated.is_default is True
    assert (await get_default_hosting_target(db_session)) is not None


@pytest.mark.asyncio
async def test_set_default_missing_raises(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="Hosting target not found"):
        await set_default_hosting_target(db_session, "nope")


@pytest.mark.asyncio
async def test_list_hosting_targets_invalid_json(db_session: AsyncSession) -> None:
    db_session.add(
        UserConfig(
            id="cfg-bad",
            config_key="hostingTargets",
            config_value="{not-json",
            version="1.0.0",
            last_device_id="webui",
            is_encrypted=False,
        )
    )
    await db_session.commit()
    assert await list_hosting_targets(db_session) == []


@pytest.mark.asyncio
async def test_get_default_hosting_target_falls_back_to_first(db_session: AsyncSession) -> None:
    await save_hosting_targets(
        db_session,
        [HostingTarget(id="only", name="Only", provider_type="vercel", config={}, is_default=False)],
    )
    default = await get_default_hosting_target(db_session)
    assert default is not None
    assert default.id == "only"


async def _store_raw_targets(db_session: AsyncSession, stored: list[dict[str, object]]) -> None:
    """Write the targets row as storage holds it, so providers the code no longer knows can be part of it."""
    db_session.add(
        UserConfig(
            id="cfg-raw-targets",
            config_key=HOSTING_TARGETS_KEY,
            config_value=stored,
            version="1.0.0",
            last_device_id="webui",
            is_encrypted=False,
        )
    )
    await db_session.commit()


def _stored(target_id: str, provider_type: str, *, is_default: bool = False) -> dict[str, object]:
    return {"id": target_id, "name": target_id, "provider_type": provider_type, "config": {}, "is_default": is_default}


@pytest.mark.asyncio
async def test_targets_of_a_provider_that_is_not_supported_are_skipped_on_read(db_session: AsyncSession) -> None:
    await _store_raw_targets(
        db_session, [_stored("n", "netlify", is_default=True), _stored("c", "cloudflare_pages"), _stored("v", "vercel")]
    )

    assert [target.id for target in await list_hosting_targets(db_session)] == ["v"]
    assert await get_hosting_target(db_session, "n") is None


@pytest.mark.asyncio
async def test_the_default_moves_to_a_supported_target_when_the_default_is_skipped(db_session: AsyncSession) -> None:
    await _store_raw_targets(db_session, [_stored("n", "netlify", is_default=True), _stored("v", "vercel")])

    default = await get_default_hosting_target(db_session)

    assert default is not None
    assert default.id == "v"


@pytest.mark.asyncio
async def test_a_skipped_target_leaves_storage_with_the_next_write(db_session: AsyncSession) -> None:
    await _store_raw_targets(db_session, [_stored("n", "netlify", is_default=True), _stored("v", "vercel")])

    await upsert_hosting_target(
        db_session, HostingTarget(id="w", name="W", provider_type="http_webhook", config={}, is_default=False)
    )

    row = (await db_session.execute(select(UserConfig).where(UserConfig.config_key == HOSTING_TARGETS_KEY))).scalars().one()
    assert isinstance(row.config_value, list)
    assert sorted(str(item["provider_type"]) for item in row.config_value) == ["http_webhook", "vercel"]
