# cron/

## Overview
Cron toolkit entry point. Aggregates scheduling engine, CRUD manager, protocols, built-in
stores, triggers, delivery, runners, and situation report aggregator. **Single SSOT for
user-facing automation** (time-based schedules plus **five wired** event triggers:
event / system_event / webhook / poll / stream via `triggers.py`; `manual` is a reserved
enum value not yet attached to `TriggerConfig`. Product wiring in
`myrm-agent-server/app/core/cron/`). Supports `skip_if_active`
concurrency control, `PreFlightCondition` script injection (probe interceptor), `context_from`
cross-task data piping (inject referenced jobs' latest successful output), incremental monitoring
(`MonitorConfig` — set/hash change detection via `infra.incremental`), and
`SituationReportBuilder` for enriching heartbeat prompts with dynamic context from registered data sources.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Cron toolkit entry point. Aggregates scheduling engine, CRUD manager, protocols, built-in | ✅ |
| _cron_tool_description.py | Core | `cron_manage_tool` LLM-visible description SSOT (EN/ZH); isolated from engine imports for prompt audits. | ✅ |
| blueprint_job_spec.py | Core | `BlueprintJobSpec`：blueprint 对其所创建的 job 的全部决定（调度、提示词、名称、能力、工具、技能、job 类型、会话模式、去重、跳过未结束的运行、超时、监控、失败告警、预检脚本、命令）的类型化冻结载体，与 `BlueprintFiller`（`(blueprint id, 槽位值, 时区) -> BlueprintJobSpec \| None`）；`DEFAULT_JOB_TIMEOUT_SECONDS` 是 spec 未声明超时时的取值，与 `CronJob` 和 `create_job` 的默认值一致（由 `tests/toolkits/cron/test_cron_blueprint_job_spec.py` 守护）。 | ✅ |
| cron_agent_tools.py | Core | Agent tool for scheduled task management. Blueprint catalog via `action=blueprints` (not Turn1 schema injection). Supports `default_delivery`, `reminder` jobs, cron-execution mutating guard, incremental monitoring, context chaining, active hours. **`required_capabilities` / `tools_allowed` / `skill_ids` CSV params** on add/update. With a blueprint, add creates the job the filled `BlueprintJobSpec` defines and forwards every spec field to `create_job` (job type, command, overlap policy, timeout, monitoring, failure alert, pre-condition script); explicit `name`, `session_mode`, `monitor_type` and the CSV lists take priority over the blueprint's values, while its prompt and schedule apply as filled (`every_minutes` or `at` next to a blueprint is rejected, a `cron_expr` is ignored), and a command the blueprint declares is not subject to the prompt/command exclusivity check that applies to a model-supplied `command`. The tool schema and description do not depend on the blueprint. | ✅ |
| delivery.py | Core | Built-in webhook ResultDelivery for cron job results. | ✅ |
| delivery_guard.py | Core | Exact-token `[SILENT]` detection for delivery filtering (`is_silent_output`). | ✅ |
| heartbeat.py | Core | Heartbeat — convenience layer over CronManager for periodic agent self-checks. Supports both INTERVAL and CRON scheduling (time-of-day triggers). Optional `agent_id` binding to inherit Agent Profile (model, prompt, skills). | ✅ |
| manager.py | Core | Cron CRUD orchestration layer. Validates job configurations, persists changes via CronStore and notifies CronScheduler. `create_job` / `update_job` accept every user-set field, including `skip_if_active` and `acceptance_criteria`. `update_job` validates the content rule on the record a patch would produce before it changes the stored job. `duplicate_job` copies every `CronJob` field with `dataclasses.replace` except the identity, the webhook credentials and the run state: a new configuration field is copied automatically, a new run-state field must be added to its reset list (`tests/toolkits/cron/test_cron_job_config_fields.py` makes every field either creatable or classified, and pins the exceptions). | ✅ |
| protocols.py | Core | Protocols for the cron toolkit. | ✅ |
| runners.py | Core | Built-in job runners (ShellJobRunner, RouterJobRunner, NotificationRunner). | ✅ |
| situation.py | Core | Situation Report — pluggable context aggregator for heartbeat ticks. SituationSection Protocol + SituationReportBuilder (concurrent build, token budget, fault-tolerant) + SituationContext. | ✅ |
| stores.py | Core | Built-in in-memory CronStore for development and testing. | ✅ |
| triggers.py | Core | Trigger type definitions and security helpers. | ✅ |
| types.py | Config | Cron job domain types. `JobType.REMINDER` for zero-LLM prompt delivery. JobResult supports `skipped` + `skip_reason` and `retry_at` (re-arm the job at an instant without counting a failure). **`CronJob.required_capabilities` + `CronJob.tools_allowed` + `CronJob.skill_ids`**; `CronJobPatch` supports `clear_tools_allowed` / `clear_skill_ids`. Agent jobs may bind **`workflow_template_id` + `workflow_template_args`** for pinned DW reruns (server runner passes through). | ✅ |

| Submodule | Description |
|-----------|-------------|
| engine/ | Cron scheduling engine internals. |
| `incident_protocols.py` | Core | Protocol contract for durable cron failure incidents ledger. | ✅ |
| `incident_types.py` | Core | Incident domain types for cron reliability and signature dedup. | ✅ |
| `incidents.py` | Core | Durable cron failure incidents with signature dedup and ack. | ✅ |
| `manager_validation.py` | Core | Cron job validation and normalization helpers. `_validate_job_content` is the one required-content rule for create and update: a shell job needs a command, a router job a prompt or a pre-condition script (it passes its input straight through), every other type a prompt. `_validate_update_content` applies it to the record an update would produce, only when the patch touches prompt, command or the pre-condition script (`tests/toolkits/cron/test_cron_job_content_rule.py`). | ✅ |

## Key Dependencies

- `core`
- `infra`
