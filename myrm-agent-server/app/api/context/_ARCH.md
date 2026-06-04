# Context API

## Overview

HTTP endpoints for context bundle health and non-destructive volume migration.

## File Index

| File | Role | Description |
|------|------|-------------|
| `router.py` | Core | `GET/PATCH /context-bundle`, migrate dry-run/apply |

## Dependencies

- `app.services.context.context_bundle_service::ContextBundleService`
- `app.schemas.context.bundle` — request/response models
