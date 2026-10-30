"""Tests for the Global Adaptive Maintenance Scheduler.

Covers: protocol types, scheduler logic, the module-level singleton and the memory-pressure hook.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from myrm_agent_harness.runtime.maintenance.protocols import (
    AgentHealthScore,
    CapacityDenial,
    CapacityTicket,
    MaintenanceTaskType,
    SystemLoadLevel,
)
from myrm_agent_harness.runtime.maintenance.scheduler import GlobalAdaptiveScheduler
from myrm_agent_harness.runtime.survival.memory_pressure import PressureEvent, PressureLevel
from tests.support.fake_load_sensor import FakeLoadSensor

# ─── protocol types ───────────────────────────────────────────────────


class TestProtocolTypes:
    def test_system_load_level_ordering(self) -> None:
        assert SystemLoadLevel.IDLE < SystemLoadLevel.NORMAL < SystemLoadLevel.BUSY < SystemLoadLevel.OVERLOADED

    def test_capacity_ticket_age(self) -> None:
        ticket = CapacityTicket(ticket_id="t1", task_type=MaintenanceTaskType.EVOLUTION)
        time.sleep(0.01)
        assert ticket.age_seconds >= 0.01

    def test_agent_health_score_needs_maintenance(self) -> None:
        healthy = AgentHealthScore(score=85)
        assert not healthy.needs_maintenance()

        unhealthy = AgentHealthScore(score=50)
        assert unhealthy.needs_maintenance()

        custom_threshold = AgentHealthScore(score=60)
        assert not custom_threshold.needs_maintenance(threshold=50)


# ─── scheduler ────────────────────────────────────────────────────────


class TestGlobalAdaptiveScheduler:
    @pytest.mark.asyncio
    async def test_grant_when_idle(self) -> None:
        sensor = FakeLoadSensor(SystemLoadLevel.IDLE)
        scheduler = GlobalAdaptiveScheduler(sensor)
        result = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        assert isinstance(result, CapacityTicket)
        assert scheduler.active_count == 1

    @pytest.mark.asyncio
    async def test_deny_when_overloaded(self) -> None:
        sensor = FakeLoadSensor(SystemLoadLevel.OVERLOADED)
        scheduler = GlobalAdaptiveScheduler(sensor)
        result = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        assert isinstance(result, CapacityDenial)
        assert scheduler.active_count == 0

    @pytest.mark.asyncio
    async def test_respects_concurrent_limit(self) -> None:
        sensor = FakeLoadSensor(SystemLoadLevel.NORMAL)
        scheduler = GlobalAdaptiveScheduler(sensor)

        t1 = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        t2 = await scheduler.request_capacity(MaintenanceTaskType.STORAGE_CLEANUP)
        t3 = await scheduler.request_capacity(MaintenanceTaskType.CONTEXT_COMPACTION)

        assert isinstance(t1, CapacityTicket)
        assert isinstance(t2, CapacityTicket)
        assert isinstance(t3, CapacityDenial)

    @pytest.mark.asyncio
    async def test_release_frees_slot(self) -> None:
        sensor = FakeLoadSensor(SystemLoadLevel.NORMAL)
        scheduler = GlobalAdaptiveScheduler(sensor)

        t1 = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        t2 = await scheduler.request_capacity(MaintenanceTaskType.STORAGE_CLEANUP)
        assert isinstance(t1, CapacityTicket)
        assert isinstance(t2, CapacityTicket)

        await scheduler.release_capacity(t1)
        assert scheduler.active_count == 1

        t3 = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        assert isinstance(t3, CapacityTicket)

    @pytest.mark.asyncio
    async def test_urgency_override(self) -> None:
        sensor = FakeLoadSensor(SystemLoadLevel.BUSY)
        scheduler = GlobalAdaptiveScheduler(sensor)

        t1 = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        assert isinstance(t1, CapacityTicket)
        await scheduler.release_capacity(t1)

        critical_health = AgentHealthScore(score=20)
        t2 = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION, health_score=critical_health)
        assert isinstance(t2, CapacityTicket)

    @pytest.mark.asyncio
    async def test_stale_ticket_expiry(self) -> None:
        sensor = FakeLoadSensor(SystemLoadLevel.NORMAL)
        scheduler = GlobalAdaptiveScheduler(sensor, ticket_ttl_seconds=0.01)

        t1 = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        assert isinstance(t1, CapacityTicket)
        assert scheduler.active_count == 1

        await asyncio.sleep(0.02)

        t2 = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        assert isinstance(t2, CapacityTicket)
        assert scheduler.active_count == 1

    @pytest.mark.asyncio
    async def test_is_idle(self) -> None:
        sensor = FakeLoadSensor(SystemLoadLevel.IDLE)
        scheduler = GlobalAdaptiveScheduler(sensor)
        assert scheduler.is_idle()

        sensor.set_level(SystemLoadLevel.BUSY)
        scheduler._last_snapshot = None
        assert not scheduler.is_idle()

    @pytest.mark.asyncio
    async def test_idle_slots(self) -> None:
        """IDLE allows 4 concurrent tasks."""
        sensor = FakeLoadSensor(SystemLoadLevel.IDLE)
        scheduler = GlobalAdaptiveScheduler(sensor)

        tickets: list[CapacityTicket] = []
        for _ in range(4):
            result = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
            assert isinstance(result, CapacityTicket)
            tickets.append(result)

        overflow = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        assert isinstance(overflow, CapacityDenial)

    @pytest.mark.asyncio
    async def test_last_snapshot_property(self) -> None:
        sensor = FakeLoadSensor(SystemLoadLevel.NORMAL)
        scheduler = GlobalAdaptiveScheduler(sensor)
        assert scheduler.last_snapshot is None

        await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        assert scheduler.last_snapshot is not None
        assert scheduler.last_snapshot.level == SystemLoadLevel.NORMAL

    @pytest.mark.asyncio
    async def test_release_nonexistent_ticket(self) -> None:
        """Releasing a ticket not in active set should not raise."""
        sensor = FakeLoadSensor(SystemLoadLevel.IDLE)
        scheduler = GlobalAdaptiveScheduler(sensor)
        fake_ticket = CapacityTicket(ticket_id="nonexistent", task_type=MaintenanceTaskType.EVOLUTION)
        await scheduler.release_capacity(fake_ticket)
        assert scheduler.active_count == 0

    @pytest.mark.asyncio
    async def test_busy_single_slot(self) -> None:
        """BUSY allows exactly 1 concurrent task."""
        sensor = FakeLoadSensor(SystemLoadLevel.BUSY)
        scheduler = GlobalAdaptiveScheduler(sensor)

        t1 = await scheduler.request_capacity(MaintenanceTaskType.STORAGE_CLEANUP)
        assert isinstance(t1, CapacityTicket)

        t2 = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        assert isinstance(t2, CapacityDenial)


# ─── singleton functions ─────────────────────────────────────────────


class TestSingletonFunctions:
    def test_get_scheduler_before_init(self) -> None:
        import myrm_agent_harness.runtime.maintenance.scheduler as sched_mod

        original = sched_mod._scheduler
        try:
            sched_mod._scheduler = None
            assert sched_mod.get_maintenance_scheduler() is None
        finally:
            sched_mod._scheduler = original

    def test_init_and_get_scheduler(self) -> None:
        import myrm_agent_harness.runtime.maintenance.scheduler as sched_mod

        original = sched_mod._scheduler
        try:
            sched_mod._scheduler = None
            sensor = FakeLoadSensor(SystemLoadLevel.NORMAL)
            with patch(
                "myrm_agent_harness.runtime.survival.memory_pressure.get_memory_pressure_monitor", return_value=None
            ):
                s = sched_mod.init_maintenance_scheduler(sensor)
            assert isinstance(s, GlobalAdaptiveScheduler)
            assert sched_mod.get_maintenance_scheduler() is s

            s2 = sched_mod.init_maintenance_scheduler(sensor)
            assert s2 is s
        finally:
            sched_mod._scheduler = original

    def test_init_subscribes_to_monitor(self) -> None:
        import myrm_agent_harness.runtime.maintenance.scheduler as sched_mod
        from myrm_agent_harness.runtime.survival.memory_pressure import MemoryPressureMonitor

        original = sched_mod._scheduler
        try:
            sched_mod._scheduler = None
            sensor = FakeLoadSensor(SystemLoadLevel.IDLE)
            mock_monitor = MemoryPressureMonitor()
            with patch(
                "myrm_agent_harness.runtime.survival.memory_pressure.get_memory_pressure_monitor",
                return_value=mock_monitor,
            ):
                s = sched_mod.init_maintenance_scheduler(sensor)
            assert s in mock_monitor._subscribers
        finally:
            sched_mod._scheduler = original


# ─── memory pressure integration ──────────────────────────────────────


class TestMemoryPressureIntegration:
    @pytest.mark.asyncio
    async def test_blocks_at_critical_pressure(self) -> None:
        sensor = FakeLoadSensor(SystemLoadLevel.IDLE)
        scheduler = GlobalAdaptiveScheduler(sensor)

        event = PressureEvent(
            level=PressureLevel.CRITICAL,
            previous_level=PressureLevel.WARNING,
            memory_percent=91.0,
            timestamp=time.monotonic(),
        )
        await scheduler.on_pressure_change(event)

        result = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        assert isinstance(result, CapacityDenial)
        assert "CRITICAL" in result.reason

    @pytest.mark.asyncio
    async def test_unblocks_after_pressure_drops(self) -> None:
        sensor = FakeLoadSensor(SystemLoadLevel.IDLE)
        scheduler = GlobalAdaptiveScheduler(sensor)

        escalate = PressureEvent(
            level=PressureLevel.EMERGENCY,
            previous_level=PressureLevel.CRITICAL,
            memory_percent=96.0,
            timestamp=time.monotonic(),
        )
        await scheduler.on_pressure_change(escalate)

        result = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        assert isinstance(result, CapacityDenial)

        de_escalate = PressureEvent(
            level=PressureLevel.WARNING,
            previous_level=PressureLevel.CRITICAL,
            memory_percent=82.0,
            timestamp=time.monotonic(),
        )
        await scheduler.on_pressure_change(de_escalate)

        result = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        assert isinstance(result, CapacityTicket)

    @pytest.mark.asyncio
    async def test_normal_pressure_allows_tasks(self) -> None:
        sensor = FakeLoadSensor(SystemLoadLevel.NORMAL)
        scheduler = GlobalAdaptiveScheduler(sensor)

        event = PressureEvent(
            level=PressureLevel.WARNING,
            previous_level=PressureLevel.NORMAL,
            memory_percent=82.0,
            timestamp=time.monotonic(),
        )
        await scheduler.on_pressure_change(event)

        result = await scheduler.request_capacity(MaintenanceTaskType.EVOLUTION)
        assert isinstance(result, CapacityTicket)
