# Context API

[INPUT]
- app.services.context.context_bundle_service::ContextBundleService (POS: bundle health and migration service)
- app.schemas.context.bundle (POS: bundle request/response models)

[OUTPUT]
- router: FastAPI router for `/context-bundle` endpoints

[POS]
HTTP endpoints for context bundle health and non-destructive volume migration.
Designed for GUI clients to query global sandbox context layout.

## File Index

| File | Role | Description |
|------|------|-------------|
| `router.py` | Core | `GET /context-bundle`, `POST /context-bundle/migrate/dry-run`, `POST /context-bundle/migrate/apply` |
