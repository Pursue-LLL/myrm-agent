# Engineering Decision Provider Architecture

## Overview
This package manages the single-node server singleton instance of `EngineeringDecisionStore` for Item 72, bridging the FastAPI HTTP API layer to the Harness memory decisions engine.

## Core Files
- `provider.py`: Thread-safe lifecycle and custom database injection helper for `EngineeringDecisionStore`.
- `__init__.py`: Public symbol re-exports conforming to server package conventions.

## Architecture Boundary
All imports from the framework layer must strictly go through `myrm_agent_harness.toolkits.memory` to satisfy the Server Architecture Import Baseline CI Gate.
