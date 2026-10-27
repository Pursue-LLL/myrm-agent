# app/channels/delegation/

## Overview
Asynchronous delegation coordination, in-flight steering pipeline, and remote approval relay subsystem. Manages delegated task lifecycles, mobile approvals, and steering tokens.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package Root | Subsystem initialization. | ✅ |
| `delegation_models.py` | Models | Core data models for tasks, steering messages, approvals, beacons, and events. | ✅ |
| `delegation_coordinator.py` | Core | Central coordinator managing task state machines, steering, remote approvals, watchdog reaping, and background execution lifecycle. The task result is the last `OutboundMessage` of the (cumulative) stream; a reply marked as a failed turn finishes the task as FAILED with its member-safe text, an exception finishes it as FAILED with the same wording (raw error only in the log), and a status already set by the reaper or `cancel_task` is never overwritten. | ✅ |
| `delegation_ingress.py` | Ingress | Channel message parsing, delegation trigger extraction, and concurrency guards. The four acknowledgements of the `/delegate` flow (task missing, quota reached, receipt, steering injected) are built by `routing/router.py` from the channel catalog (`delegation_*` in `i18n/locales`) in the sender's locale; the text of `build_receipt_card_content`, the delivery and approval cards of `delegation_delivery.py`, and the failure notice of the coordinator are still Chinese only. | ✅ |
| `delegation_delivery.py` | Delivery | Multi-channel delivery for progress beacons, workspace artifact scanning, 20MB limit fallback, and rich cards; the card title follows the final status (completed / failed / cancelled). | ✅ |
| `trajectory_aggregator.py` | Aggregator | Collects multi-source task execution, artifacts, and decisions into structured trajectory items. | ✅ |
| `weekly_report_sop.py` | SOP Service | Generates executive Markdown weekly reports and archives group chat decisions to wiki articles. | ✅ |


## Key Dependencies

- `app.channels` (underlying channel transports)
- `myrm_agent_harness.utils.runtime.steering` (steering tokens)
- `myrm_agent_harness.utils.runtime.cancellation` (cancellation tokens)
