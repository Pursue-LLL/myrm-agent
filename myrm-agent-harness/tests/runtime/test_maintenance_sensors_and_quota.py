"""Tests for the maintenance load sensors and the scheduler's gate on storage-quota cleanup.

Covers: DeviceLoadSensor and SaaSLoadSensor classification and real read paths, and the integration with
SimpleStorageQuotaManager.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.runtime.maintenance.protocols import SystemLoadLevel, SystemLoadSnapshot
from myrm_agent_harness.runtime.maintenance.scheduler import GlobalAdaptiveScheduler
from myrm_agent_harness.runtime.maintenance.sensors import DeviceLoadSensor, SaaSLoadSensor
from myrm_agent_harness.runtime.quota.manager import SimpleStorageQuotaManager
from tests.support.fake_load_sensor import FakeLoadSensor

# ─── sensors ──────────────────────────────────────────────────────────


class TestDeviceLoadSensor:
    def test_classify_idle(self) -> None:
        sensor = DeviceLoadSensor()
        level = sensor._classify(cpu=5.0, mem=30.0)
        assert level == SystemLoadLevel.IDLE

    def test_classify_normal(self) -> None:
        sensor = DeviceLoadSensor()
        level = sensor._classify(cpu=40.0, mem=55.0)
        assert level == SystemLoadLevel.NORMAL

    def test_classify_busy(self) -> None:
        sensor = DeviceLoadSensor()
        level = sensor._classify(cpu=70.0, mem=55.0)
        assert level == SystemLoadLevel.BUSY

    def test_classify_overloaded(self) -> None:
        sensor = DeviceLoadSensor()
        level = sensor._classify(cpu=90.0, mem=55.0)
        assert level == SystemLoadLevel.OVERLOADED

    def test_classify_mem_overloaded(self) -> None:
        sensor = DeviceLoadSensor()
        level = sensor._classify(cpu=20.0, mem=95.0)
        assert level == SystemLoadLevel.OVERLOADED


class TestSaaSLoadSensor:
    def test_stale_data_returns_normal(self) -> None:
        sensor = SaaSLoadSensor()
        snapshot = sensor.read()
        assert snapshot.level == SystemLoadLevel.NORMAL

    def test_fresh_idle(self) -> None:
        sensor = SaaSLoadSensor()
        sensor.update(api_quota_remaining_pct=90.0, queue_depth=2)
        snapshot = sensor.read()
        assert snapshot.level == SystemLoadLevel.IDLE

    def test_fresh_overloaded(self) -> None:
        sensor = SaaSLoadSensor()
        sensor.update(api_quota_remaining_pct=5.0, queue_depth=200)
        snapshot = sensor.read()
        assert snapshot.level == SystemLoadLevel.OVERLOADED

    def test_fresh_busy(self) -> None:
        sensor = SaaSLoadSensor()
        sensor.update(api_quota_remaining_pct=20.0, queue_depth=30)
        snapshot = sensor.read()
        assert snapshot.level == SystemLoadLevel.BUSY


# ─── sensors: real read paths ─────────────────────────────────────────


class TestDeviceLoadSensorRead:
    def test_read_with_psutil(self) -> None:
        sensor = DeviceLoadSensor()
        snapshot = sensor.read()
        assert isinstance(snapshot, SystemLoadSnapshot)
        assert snapshot.cpu_percent >= 0.0
        assert snapshot.memory_percent >= 0.0
        assert snapshot.detail

    def test_read_without_psutil(self) -> None:
        with patch("myrm_agent_harness.runtime.maintenance.sensors.psutil", None):
            sensor = DeviceLoadSensor()
            snapshot = sensor.read()
            assert snapshot.level == SystemLoadLevel.NORMAL
            assert "psutil unavailable" in snapshot.detail


class TestSaaSLoadSensorClassify:
    def test_classify_normal(self) -> None:
        """api_quota between 30-80 and moderate queue => NORMAL."""
        sensor = SaaSLoadSensor()
        sensor.update(api_quota_remaining_pct=50.0, queue_depth=20)
        snapshot = sensor.read()
        assert snapshot.level == SystemLoadLevel.NORMAL


# ─── integration: SimpleStorageQuotaManager ───────────────────────────


class TestQuotaManagerIntegration:
    @pytest.mark.asyncio
    async def test_cleanup_deferred_when_overloaded(self, tmp_path: Path) -> None:
        context_root = tmp_path / ".context"
        context_root.mkdir()

        sensor = FakeLoadSensor(SystemLoadLevel.OVERLOADED)
        scheduler = GlobalAdaptiveScheduler(sensor)

        mgr = SimpleStorageQuotaManager(
            per_session_limit=2000,
            auto_cleanup_threshold=0.5,
            context_root=str(context_root),
            scheduler=scheduler,
        )

        session_dir = context_root / "s1" / "compacted"
        session_dir.mkdir(parents=True)
        for i in range(5):
            (session_dir / f"f{i}.txt").write_text("x" * 200)

        allowed = await mgr.check_write_allowed("s1", 10)
        assert allowed is True

        remaining_files = list(session_dir.iterdir())
        assert len(remaining_files) == 5

    @pytest.mark.asyncio
    async def test_cleanup_runs_when_idle(self, tmp_path: Path) -> None:
        context_root = tmp_path / ".context"
        context_root.mkdir()

        sensor = FakeLoadSensor(SystemLoadLevel.IDLE)
        scheduler = GlobalAdaptiveScheduler(sensor)

        mgr = SimpleStorageQuotaManager(
            per_session_limit=1500,
            auto_cleanup_threshold=0.5,
            context_root=str(context_root),
            scheduler=scheduler,
        )

        session_dir = context_root / "s1" / "compacted"
        session_dir.mkdir(parents=True)
        for i in range(5):
            (session_dir / f"f{i}.txt").write_text("x" * 200)

        allowed = await mgr.check_write_allowed("s1", 10)
        assert allowed is True

        remaining_files = list(session_dir.iterdir())
        assert len(remaining_files) < 5

    @pytest.mark.asyncio
    async def test_write_rejected_over_limit(self, tmp_path: Path) -> None:
        context_root = tmp_path / ".context"
        context_root.mkdir()

        mgr = SimpleStorageQuotaManager(
            per_session_limit=100,
            context_root=str(context_root),
        )

        session_dir = context_root / "s1" / "compacted"
        session_dir.mkdir(parents=True)
        (session_dir / "big.txt").write_text("x" * 80)

        allowed = await mgr.check_write_allowed("s1", 50)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_get_remaining_quota(self, tmp_path: Path) -> None:
        context_root = tmp_path / ".context"
        context_root.mkdir()

        mgr = SimpleStorageQuotaManager(
            per_session_limit=1000,
            context_root=str(context_root),
        )

        remaining = await mgr.get_remaining_quota("empty_session")
        assert remaining == 1000

        session_dir = context_root / "s2" / "compacted"
        session_dir.mkdir(parents=True)
        (session_dir / "f1.txt").write_text("x" * 200)

        remaining = await mgr.get_remaining_quota("s2")
        assert remaining == 800

    @pytest.mark.asyncio
    async def test_invalidate_cache(self, tmp_path: Path) -> None:
        context_root = tmp_path / ".context"
        context_root.mkdir()

        mgr = SimpleStorageQuotaManager(
            per_session_limit=1000,
            context_root=str(context_root),
        )

        session_dir = context_root / "s1" / "compacted"
        session_dir.mkdir(parents=True)
        (session_dir / "f1.txt").write_text("x" * 100)

        await mgr.get_remaining_quota("s1")
        assert "s1" in mgr._usage_cache

        mgr.invalidate_cache("s1")
        assert "s1" not in mgr._usage_cache

        await mgr.get_remaining_quota("s1")
        mgr.invalidate_cache()
        assert len(mgr._usage_cache) == 0

    @pytest.mark.asyncio
    async def test_cleanup_without_scheduler(self, tmp_path: Path) -> None:
        """Auto-cleanup works even without a scheduler."""
        context_root = tmp_path / ".context"
        context_root.mkdir()

        mgr = SimpleStorageQuotaManager(
            per_session_limit=1500,
            auto_cleanup_threshold=0.5,
            context_root=str(context_root),
        )

        session_dir = context_root / "s1" / "compacted"
        session_dir.mkdir(parents=True)
        for i in range(5):
            (session_dir / f"f{i}.txt").write_text("x" * 200)

        allowed = await mgr.check_write_allowed("s1", 10)
        assert allowed is True

        remaining_files = list(session_dir.iterdir())
        assert len(remaining_files) < 5

    @pytest.mark.asyncio
    async def test_nonexistent_session_dir(self, tmp_path: Path) -> None:
        context_root = tmp_path / ".context"
        context_root.mkdir()

        mgr = SimpleStorageQuotaManager(
            per_session_limit=1000,
            context_root=str(context_root),
        )

        allowed = await mgr.check_write_allowed("ghost_session", 100)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_usage_cache_hit(self, tmp_path: Path) -> None:
        context_root = tmp_path / ".context"
        context_root.mkdir()

        mgr = SimpleStorageQuotaManager(
            per_session_limit=1000,
            context_root=str(context_root),
        )

        session_dir = context_root / "s1" / "compacted"
        session_dir.mkdir(parents=True)
        (session_dir / "f1.txt").write_text("x" * 100)

        await mgr.check_write_allowed("s1", 10)
        assert "s1" in mgr._usage_cache

        allowed = await mgr.check_write_allowed("s1", 10)
        assert allowed is True
