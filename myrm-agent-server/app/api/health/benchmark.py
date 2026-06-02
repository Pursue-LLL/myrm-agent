"""[INPUT]
- events.event_bus::AppEvent (POS: Immutable event payload broadcast to all SSE subscribers.)
- events.event_bus::AppEventType (POS: Known event types pushed to web clients.)
- events.event_bus::get_event_bus (POS: Singleton accessor — lazily created on first call.)

[OUTPUT]
- router: APIRouter for benchmark endpoints.
- run_benchmark: POST /api/v1/health/benchmark

[POS]
Provides asynchronous performance benchmark execution and SSE streaming.
"""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks

from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health", "benchmark"])


async def _execute_benchmarks() -> None:
    """Run all benchmarks and stream progress via SSE."""
    from myrm_agent_harness.observability.diagnostics.performance import _benchmark_hooks
    from myrm_agent_harness.observability.diagnostics.protocols import HealthReport
    
    bus = get_event_bus()
    total = len(_benchmark_hooks)
    
    bus.publish(
        AppEvent(
            event_type=AppEventType.BENCHMARK_PROGRESS,
            data={
                "status": "started",
                "progress": 0,
                "total": total,
                "message": "Starting performance benchmark suite...",
            },
        )
    )
    
    reports: list[HealthReport] = []
    
    for idx, hook in enumerate(_benchmark_hooks):
        hook_name = getattr(hook, "__name__", f"hook_{idx}")
        
        bus.publish(
            AppEvent(
                event_type=AppEventType.BENCHMARK_PROGRESS,
                data={
                    "status": "running",
                    "progress": idx,
                    "total": total,
                    "current_task": hook_name,
                    "message": f"Running {hook_name}...",
                },
            )
        )
        
        try:
            async with asyncio.timeout(15.0):
                report = await hook()
                reports.append(report)
        except TimeoutError:
            report = HealthReport(
                component_name=hook_name,
                status="fail",
                message="Benchmark timed out.",
                detail="Benchmark timed out (>15s).",
                fix_suggestion="Check network or API provider.",
            )
            reports.append(report)
        except Exception as e:
            report = HealthReport(
                component_name=hook_name,
                status="fail",
                message="Benchmark encountered an unexpected error.",
                detail=f"Benchmark raised an uncaught exception: {e}",
                fix_suggestion="Check application logs for details.",
            )
            reports.append(report)
            
        # Optional: Save to history if we want to track TTFT over time
        # This could be added later or done synchronously here.
            
    bus.publish(
        AppEvent(
            event_type=AppEventType.BENCHMARK_PROGRESS,
            data={
                "status": "completed",
                "progress": total,
                "total": total,
                "message": "Benchmark suite completed.",
                "reports": [r.model_dump() for r in reports],
            },
        )
    )


@router.post("/benchmark")
async def run_benchmark(background_tasks: BackgroundTasks) -> dict[str, str]:
    """Trigger an asynchronous performance benchmark suite.
    
    Results are streamed via SSE (AppEventType.BENCHMARK_PROGRESS).
    """
    background_tasks.add_task(_execute_benchmarks)
    return {"status": "accepted", "message": "Benchmark started. Listen to SSE for progress."}
