# app/channels/delegation/

## Overview
Asynchronous delegation of long-running chat requests: a `/delegate` (or detected long-task) message runs in the background while the chat stays free, in-flight messages steer the running task, and the outcome is delivered back to the originating chat. Manages delegated task lifecycles and steering tokens.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package Root | Subsystem initialization. | ✅ |
| `delegation_models.py` | Models | `DelegationStatus`, `DelegationTask` and `DeliveryArtifact`. | ✅ |
| `delegation_coordinator.py` | Core | Central coordinator managing task state machines, steering, watchdog reaping, and background execution lifecycle. The task result is the last `OutboundMessage` of the (cumulative) stream; a reply marked as a failed turn finishes the task as FAILED with its member-safe text, an exception finishes it as FAILED with the same wording (raw error only in the log), and a status already set by the reaper is never overwritten. | ✅ |
| `delegation_ingress.py` | Ingress | Channel message parsing, delegation trigger extraction, and the per-user concurrency guard. The four acknowledgements of the `/delegate` flow (task missing, quota reached, receipt, steering injected) are built by `routing/router.py` from the channel catalog (`delegation_*` in `i18n/locales`) in the sender's locale; the delivery card of `delegation_delivery.py` and the failure notice of the coordinator are still Chinese only. | ✅ |
| `delegation_delivery.py` | Delivery | Workspace artifact scanning, 20MB limit fallback, and the completion card; the card title follows the final status (completed / failed). | ✅ |


## Key Dependencies

- `app.channels` (underlying channel transports)
- `myrm_agent_harness.utils.runtime.steering` (steering tokens)
- `myrm_agent_harness.utils.runtime.cancellation` (cancellation tokens)
