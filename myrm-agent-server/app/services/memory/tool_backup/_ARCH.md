# Durable Tool Use Backup Provider Architecture

## Overview
This package manages the single-node server singleton instance of `ToolUseBackupService` for Item 74, bridging the FastAPI HTTP API layer to the Harness durable tool use side-index engine.

## Core Files
- `provider.py`: Thread-safe lifecycle and custom database injection helper for `ToolUseBackupService`.
- `__init__.py`: Public symbol re-exports conforming to server package conventions.

## Architecture Boundary
All imports from the framework layer must strictly go through `myrm_agent_harness.toolkits.memory` to satisfy the Server Architecture Import Baseline CI Gate.
