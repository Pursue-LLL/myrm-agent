# Context Virtual File System Provider Architecture

## Overview
This package manages the server-side singleton lifecycle and FastAPI dependency injection for `ContextVirtualFileSystem` (Item 77). It coordinates deterministic hierarchy navigation, virtual file writes, content reads, and keyword search across sandboxed sessions.

## Core Modules
- `provider.py`: `ContextVFSProvider` singleton manager and `get_context_vfs()` dependency injection helper.
- `__init__.py`: Public package exports.
