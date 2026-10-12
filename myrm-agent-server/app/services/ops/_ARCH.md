# Ops Services Architecture

## Overview
This module provides operational snapshot and diagnostic services for sandbox and server runtime.

## Components
- `snapshot_service.py`: Collects system and sandbox runtime metrics, health stats, and diagnostic logs. `_collect_memory_info` reads `memory_operation_events` (ERROR → `failed_event_count`, degraded), `memory_extract_retries` pending depth → `queue_backlog`, and sets `critical` when the ledger probe fails.
