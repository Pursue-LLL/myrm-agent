"""Unit tests for EntitlementGuardedCronManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.cron.adapters.entitlement_guarded_manager import EntitlementGuardedCronManager
from app.platform_utils.sandbox.entitlements.entitlement_guard import EntitlementGuardError

_SLOT_FN = "app.platform_utils.sandbox.entitlements.entitlement_guard.require_cron_slot"


@pytest.mark.asyncio
async def test_create_job_enforces_slot_before_inner() -> None:
    inner = MagicMock()
    inner.count_jobs = AsyncMock(return_value=2)
    inner.create_job = AsyncMock(return_value=MagicMock(id="job-1"))
    mgr = EntitlementGuardedCronManager(inner)

    with patch(_SLOT_FN) as mock_slot:
        await mgr.create_job("user-1", name="t", job_type=MagicMock(), schedule=MagicMock())

    inner.count_jobs.assert_awaited_once_with("user-1")
    mock_slot.assert_called_once_with(2)
    inner.create_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_job_maps_entitlement_error_to_value_error() -> None:
    inner = MagicMock()
    inner.count_jobs = AsyncMock(return_value=0)
    mgr = EntitlementGuardedCronManager(inner)

    with patch(_SLOT_FN, side_effect=EntitlementGuardError("upgrade required")):
        with pytest.raises(ValueError, match="upgrade required") as exc_info:
            await mgr.create_job("user-1", name="t", job_type=MagicMock(), schedule=MagicMock())

    assert isinstance(exc_info.value.__cause__, EntitlementGuardError)
    inner.create_job.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_job_delegates_after_slot_check() -> None:
    inner = MagicMock()
    inner.count_jobs = AsyncMock(return_value=1)
    inner.duplicate_job = AsyncMock(return_value=MagicMock(id="dup-1"))
    mgr = EntitlementGuardedCronManager(inner)

    with patch(_SLOT_FN):
        result = await mgr.duplicate_job("src-id", "user-1")

    assert result is not None
    inner.duplicate_job.assert_awaited_once_with("src-id", "user-1")


@pytest.mark.asyncio
async def test_duplicate_job_maps_entitlement_error_to_value_error() -> None:
    inner = MagicMock()
    inner.count_jobs = AsyncMock(return_value=0)
    mgr = EntitlementGuardedCronManager(inner)

    with patch(_SLOT_FN, side_effect=EntitlementGuardError("duplicate blocked")):
        with pytest.raises(ValueError, match="duplicate blocked"):
            await mgr.duplicate_job("src-id", "user-1")

    inner.duplicate_job.assert_not_called()


def test_getattr_delegates_to_inner() -> None:
    inner = MagicMock()
    inner.list_jobs = MagicMock(return_value=["job-a"])
    mgr = EntitlementGuardedCronManager(inner)

    assert mgr.list_jobs is inner.list_jobs
