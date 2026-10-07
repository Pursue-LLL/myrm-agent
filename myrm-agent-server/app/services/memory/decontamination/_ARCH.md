# Memory Decontamination Provider Architecture

## Overview
This package manages the server-side singleton lifecycle and FastAPI dependency injection for `MemoryProvenanceDecontaminationService` (Item 76). It coordinates tamper-evident provenance validation, active threat quarantine, and point-in-time snapshot rollbacks.

## Core Modules
- `provider.py`: `MemoryDecontaminationProvider` singleton manager and `get_decontamination_service()` dependency injection helper.
- `__init__.py`: Public package exports.
