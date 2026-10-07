# Embedded SQLite-Vec Service Architecture

## Position
Server-side business orchestration and lifecycle provider for embedded single-file SQLite vector store, managing singleton database lifecycle, telemetry, and retrieval dispatch.

## Core Design Principles
1. **Single-User Sandbox Isolation**: Direct access to local storage in sandbox volume (`data/memory_vector.db`) without multi-tenant crosstalk.
2. **Dual-Track Status Observability**: Surfaces whether hardware-accelerated SIMD (`native_vec0`) or zero-daemon software fallback (`process_blob`) is active.
3. **Decay Aware Retrieval**: Orchestrates dense similarity retrieval enriched with temporal decay factors for clean injection into downstream prompt pipelines.
