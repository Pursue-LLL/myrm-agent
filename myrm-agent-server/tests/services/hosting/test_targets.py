"""Unit tests for hosting targets CRUD."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.hosting.targets import (
    delete_hosting_target,
    get_default_hosting_target,
    get_default_hosting_target_from_list,
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
        HostingTarget(id="t2", name="Netlify", provider_type="netlify", config={"site_id": "s1"}, is_default=False),
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
        HostingTarget(id="b", name="B", provider_type="netlify", config={}, is_default=True),
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


def test_get_default_hosting_target_from_list() -> None:
    targets = [
        HostingTarget(id="a", name="A", provider_type="vercel", config={}, is_default=False),
        HostingTarget(id="b", name="B", provider_type="vercel", config={}, is_default=True),
    ]
    assert get_default_hosting_target_from_list(targets) is not None
    assert get_default_hosting_target_from_list([]) is None


@pytest.mark.asyncio
async def test_list_hosting_targets_invalid_json(db_session: AsyncSession) -> None:
    from app.database.models.config import UserConfig

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
