# app/channels/delegation/

## Overview
Asynchronous delegation coordination, in-flight steering pipeline, and remote approval relay subsystem. Manages delegated task lifecycles, mobile approvals, and steering tokens.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package Root | Subsystem initialization. | ✅ |
| `delegation_models.py` | Models | Core data models for tasks, steering messages, approvals, beacons, and events. | ✅ |
| `delegation_coordinator.py` | Core | Central coordinator managing task state machines, steering, and remote approvals. | ✅ |
| `delegation_ingress.py` | Ingress | Channel message parsing, delegation trigger extraction, and permission checks. | ✅ |
| `delegation_delivery.py` | Delivery | Multi-channel delivery for progress beacons and approval prompts. | ✅ |

## Key Dependencies

- `app.channels` (underlying channel transports)
- `myrm_agent_harness.utils.runtime.steering` (steering tokens)
- `myrm_agent_harness.utils.runtime.cancellation` (cancellation tokens)
