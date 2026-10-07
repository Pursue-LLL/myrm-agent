# Context Ingestion Provider Architecture

## Overview
This package manages the server-side lifecycle and dependency injection for the `UniversalContextIngestionGateway` (Item 75). It ensures single-instance deduplication across long-running server sessions, sandbox processes, and incoming hardware webhooks.

## Core Modules
- `provider.py`: `ContextIngestionProvider` singleton and `get_context_ingestion_gateway()` dependency injection helper.
- `__init__.py`: Public package exports.
