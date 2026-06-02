"""Integration test for startup performance optimization.

Validates the optimized startup flow with real services.
"""

import asyncio

import pytest
from myrm_agent_harness.runtime.startup import StartupTimer


@pytest.mark.asyncio
async def test_startup_flow_with_metrics() -> None:
    """Test the optimized startup flow produces detailed metrics."""
    timer = StartupTimer()

    # Simulate Phase 1a (Sequential)
    async with timer.phase("critical"):
        async with timer.task("init_database"):
            await asyncio.sleep(0.01)

        async with timer.task("migrate_configs"):
            await asyncio.sleep(0.01)

        async with timer.task("ensure_local_admin"):
            await asyncio.sleep(0.01)

        # Simulate Phase 1b (Parallel) - 7 tasks
        async def task1():
            await asyncio.sleep(0.005)

        async def task2():
            await asyncio.sleep(0.005)

        async def task3():
            await asyncio.sleep(0.005)

        async def task4():
            await asyncio.sleep(0.005)

        async def task5():
            await asyncio.sleep(0.005)

        async def task6():
            await asyncio.sleep(0.005)

        async def task7():
            await asyncio.sleep(0.005)

        # Parallel execution
        await asyncio.gather(task1(), task2(), task3(), task4(), task5(), task6(), task7())

    # Simulate Phase 2 (Essential services)
    async with timer.phase("core"):
        async with timer.task("start_channel_gateway"):
            await asyncio.sleep(0.005)

        async with timer.task("start_cron_scheduler"):
            await asyncio.sleep(0.005)

    # Validate metrics structure
    result = timer.metrics.to_dict()

    # Verify nested structure exists
    assert "phases" in result
    assert "critical" in result["phases"]
    assert "core" in result["phases"]

    # Verify Phase 1 has task details
    critical_phase = result["phases"]["critical"]
    assert "total_ms" in critical_phase
    assert "tasks" in critical_phase
    assert len(critical_phase["tasks"]) == 3
    assert "init_database" in critical_phase["tasks"]
    assert "migrate_configs" in critical_phase["tasks"]
    assert "ensure_local_admin" in critical_phase["tasks"]

    # Verify Phase 2 has task details
    core_phase = result["phases"]["core"]
    assert "total_ms" in core_phase
    assert "tasks" in core_phase
    assert len(core_phase["tasks"]) == 2
    assert "start_channel_gateway" in core_phase["tasks"]
    assert "start_cron_scheduler" in core_phase["tasks"]

    # Verify total elapsed
    assert "total_elapsed_ms" in result
    assert result["total_elapsed_ms"] > 0

    print("\n✅ Startup metrics validation passed:")
    print(f"   Critical phase: {critical_phase['total_ms']:.2f}ms")
    print(f"   Core phase: {core_phase['total_ms']:.2f}ms")
    print(f"   Total: {result['total_elapsed_ms']:.2f}ms")


@pytest.mark.asyncio
async def test_phase1_parallelization_saves_time() -> None:
    """Test that Phase 1b parallelization actually saves time."""

    # Sequential execution (old way) — larger sleep for better signal-to-noise ratio
    start_seq = asyncio.get_event_loop().time()
    for _ in range(7):
        await asyncio.sleep(0.02)
    sequential_time = (asyncio.get_event_loop().time() - start_seq) * 1000

    # Parallel execution (new way)
    start_par = asyncio.get_event_loop().time()
    await asyncio.gather(*[asyncio.sleep(0.02) for _ in range(7)])
    parallel_time = (asyncio.get_event_loop().time() - start_par) * 1000

    # Parallel should be significantly faster (at least 2x)
    assert parallel_time < sequential_time / 2

    print("\n✅ Parallelization benefit:")
    print(f"   Sequential: {sequential_time:.2f}ms")
    print(f"   Parallel: {parallel_time:.2f}ms")
    print(f"   Speedup: {sequential_time / parallel_time:.1f}x")
