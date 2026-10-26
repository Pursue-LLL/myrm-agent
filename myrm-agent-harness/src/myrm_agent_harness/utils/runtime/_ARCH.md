# runtime/

## Overview
Agent run() lifecycle control parameters. All based on ContextVar for request-level isolation.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Agent run() lifecycle control parameters. All based on ContextVar for request-level isolation. | — |
| cancellation.py | Core | Cancellation token + CancellationRegistry（cancel / cancel_all for E-Stop）+ `run_until_cancelled`（token 取消时中止仍阻塞在驱动调用上的操作，轮询 0.25s，取消后最多 3s 收尾；调用方自身被取消时一并取消内部任务）+ `reraise_if_cancelled`（`except asyncio.CancelledError` 里唯一的取消判定规则：仅当 `Task.cancelling() > 0`，即确有一次针对本任务的停止请求时重新抛出，否则放行——SDK cancel scope 漏出的取消与 `gather(return_exceptions=True)` 交回的已取消子任务都不算本任务被停） | ✅ |
| cancellation_metrics.py | Core | Cancellation metrics data structures. | ✅ |
| progress_sink.py | Core | Progress event push mechanism. Tools implicitly obtain a sink via ContextVar to push intermediate pr | ✅ |
| steering.py | Core | Steering token mechanism. Allows external message injection (steer/redirect) during Agent runtime. Steer waits for tool boundary; redirect immediately breaks astream and preserves partial output. | ✅ |
| wakeup_registry.py | Core | Global registry for async wakeup events (Idle Wakeup). | ✅ |
| user_control.py | Core | Process-wide truth of "a person drives the agent's browser/desktop" (`UserControl`: held + generation) and `apply_user_control_gate`: tool-level fence that waits every non-exempt tool while held and refuses acting tools on a page the model has not re-observed since control returned. Stopping the run ends any wait on a person (`wait_released` races the run's cancel token and raises `OperationCancelledError`); a gate given `cancelled_result` returns it instead (desktop), one without lets the stop rise to the toolkit's cancel boundary (browser). Browser and desktop toolkits only consult it (no push into sessions). `planned_against` / `plan_is_stale` pin the steps of one multi-step plan (a browser script) to the hand-over it was planned against, so a later step can tell that a person used the surface meanwhile. | ✅ |
| background_job_finish_registry.py | Core | ``BackgroundJobFinishResult`` DTO + ``BackgroundJobFinishHandler`` Protocol; server registers handler at warmup for natural bash background job ``exited`` events (no headless LLM). | ✅ |

## Key Dependencies

- `agent`
