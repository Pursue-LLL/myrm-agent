# services/models/

## Overview

Model capability management, context configuration, and pricing override engines.

## Subdirectories

| Directory | Role | Description | Architecture |
|-----------|------|-------------|--------------|
| `overrides/` | Core | User custom model context window and pricing override registry | [overrides/_ARCH.md](overrides/_ARCH.md) |

## Dependencies

- `pydantic`
- `app.services.models.overrides`
