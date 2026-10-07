# Batch Memory Learning Server Service Architecture

## 1. Role and Boundaries
This service manages the lifecycle of the `BatchMemoryLearningService` singleton for `myrm-agent-server`.
It bridges incoming FastAPI HTTP requests with the resilient batch chunk processor in `myrm-agent-harness`.

- **Single-Machine Sandbox**: Stores SQLite audit ledger inside the user's isolated sandbox volume (`/tmp/myrm_data/myrm_batch_learn.db` or configured path).
- **Zero Multi-tenant Logic**: Strict local single-tenant execution context.
- **Dependency Injection**: Exposes `get_batch_learning_service` for clean FastAPI endpoint dependency resolution.
