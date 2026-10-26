# engine/

## Overview
Cron scheduling engine internals.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Cron scheduling engine internals. | — |
| connector_health.py | Core | Structured connector health degradation and failure classification for cron automations. | 纯 |
| executor.py | Core | Single-job execution lifecycle. Delivery gate: incremental skip, `is_silent_output`, output-hash dedup；`monitor_contract_error`（invalid JSON-like）显式记录并按失败链路进入统一告警，重复 contract error 会抑制主通道重复投递；failure 计数持久化异常时回退内存计数保证去重稳定。The closing write (`_update_after_run`) adopts the stored job first (`job_freshness.py`), then applies what the run decided (auto-pause, backoff, completion). Runner-level skips and `JobResult.retry_at` deferrals are recorded by `SkippedRunMixin` (`skipped_runs.py`). | ✅ |
| fingerprint.py | Core | Canonical workflow fingerprint hashing for automation manual success prerequisite gating. | 纯 |
| helpers.py | Core | Provides resolve_stagger_ms, is_top_of_hour_cron, compute_stagger_offset_s. | ✅ |
| integrity.py | Core | Merkle chain integrity for cron run records. | ✅ |
| job_freshness.py | Core | `adopt_latest(store, job)`: the stored job is the truth. Copies every `CronJob` field except the run-owned `RUN_OWNED_FIELDS` (`fire_count`, `last_output_hash`) from the store onto an in-hand snapshot; `False` when the job was deleted. Called after the stagger and slot waits (`scheduler.py`) and before each closing write (`executor.py`, `skipped_runs.py`), so a pause, edit or delete made while a run waited or ran is neither undone nor resurrected. A new run-owned `CronJob` field must be added to `RUN_OWNED_FIELDS` (a test pins the set to real fields). | ✅ |
| name_generator.py | Core | Intelligently truncates long prompts/commands while preserving readability. | ✅ |
| parser.py | Core | Cron expression parsing and next-run calculation. | ✅ |
| recovery.py | Core | Three-phase startup recovery strategy. | ✅ |
| skipped_runs.py | Core | `SkippedRunMixin` mixed into `JobExecutor`: `_record_skipped()` writes a SKIPPED run and advances the schedule (one-shot jobs complete or are deleted); `_record_deferred()` handles `JobResult.retry_at` — SKIPPED run, no failure counted, job re-armed at the instant, one-shot jobs stay alive. Both adopt the stored job first: a deleted job gets no run record and is not brought back, a paused job stays paused. | ✅ |
| scheduler.py | Core | Cron scheduling engine. Computes exact sleep durations to the next due job and dispatches due jobs into async tasks bounded by a global and a per-user semaphore. After the stagger and slot waits a run starts only if the stored job still exists and is ACTIVE (`adopt_latest`), and then runs the stored definition. | ✅ |
| `cron_job_adapter.py` | Core | Cron 任务与不可摧毁作业系统桥接适配器。 — CronExecutionDecision; CronJobEvaluationResult; CronJobAdapter | ✅ |

## Key Dependencies

- `infra`
- `observability.tracing` (TracingContext for per-execution trace_id/session_id)
