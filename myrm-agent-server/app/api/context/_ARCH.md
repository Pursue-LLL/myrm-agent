# Context API

[INPUT]
- app.services.context.context_bundle_service::ContextBundleService (POS: bundle health and migration service)
- app.schemas.context.bundle (POS: bundle request/response models)

[OUTPUT]
- router: FastAPI router for /context-bundle and /context-search endpoints

[POS]
HTTP endpoints for context bundle health, non-destructive volume migration, and unified context search.
Designed for GUI clients (like MemoryCommandCenterDoctorPanel) to query global sandbox context.

## File Index

| File | Role | Description |
|------|------|-------------|
| `router.py` | Core | `GET /context-bundle`, migrate dry-run/apply, `GET /context-search` |
