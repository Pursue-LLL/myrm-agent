# Memory Repair Provider Architecture

## Overview
This package manages the single-node server singleton instance of `MemoryRepairService` for Item 73, bridging the FastAPI HTTP API layer to the Harness memory integrity repair and stale pruning engine.

## Core Files
- `provider.py`: Thread-safe lifecycle and custom database injection helper for `MemoryRepairService`.
- `__init__.py`: Public symbol re-exports conforming to server package conventions.

## Architecture Boundary
All imports from the framework layer must strictly go through `myrm_agent_harness.toolkits.memory` to satisfy the Server Architecture Import Baseline CI Gate.
