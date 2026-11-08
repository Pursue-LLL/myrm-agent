"""[INPUT]
- pydantic / pydantic_settings (POS: validated, env-backed settings)

[OUTPUT]
- MessageFilterSettings, MonitoringSettings, DatabaseSettings, ServiceSettings, ControlPlaneSettings, ContextCompactionTelemetrySettings, MemoryBriefStatusTelemetrySettings, ExecutionCacheSettings, MemoryGuardianGuardTelemetrySettings

[POS]
Application settings: database, service, control-plane, monitoring and telemetry settings.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class MessageFilterSettings(BaseSettings):
    """System-role injection filter for chat context construction."""

    model_config = SettingsConfigDict(env_prefix="")

    enabled: bool = Field(default=True, validation_alias="MESSAGE_FILTER_ENABLED")
    admin_api_keys: str = Field(
        default="",
        validation_alias="ADMIN_API_KEYS",
        description="Comma-separated API keys bypassing the filter",
    )

    def whitelist_api_keys(self) -> set[str]:
        if not self.admin_api_keys.strip():
            return set()
        return {key.strip() for key in self.admin_api_keys.split(",") if key.strip()}


class MonitoringSettings(BaseSettings):
    """Prometheus metrics toggle. OpenTelemetry export is configured purely by the standard ``OTEL_*`` variables."""

    model_config = SettingsConfigDict(env_prefix="")

    metrics_enabled: bool = Field(default=False, validation_alias="METRICS_ENABLED")


class DatabaseSettings(BaseSettings):
    """Workspace layout and database connection parameters."""

    model_config = SettingsConfigDict(env_prefix="")

    state_dir: str = Field(
        default="~/.myrm",
        validation_alias="MYRM_DATA_DIR",
        description="[P] Root data directory; all derived paths hang off this",
    )
    sqlite_path: str = ""  # Derived: {state_dir}/data.db
    qdrant_path: str = ""  # Derived: {state_dir}/qdrant
    sqlite_db_path: str = ""  # Derived: {state_dir}/checkpoints.db
    harness_dir: str = ""  # Derived: {state_dir}/harness
    event_log_dir: str = Field(default="", validation_alias="EVENT_LOG_DIR")
    memory_base_path: str = Field(default="", validation_alias="MEMORY_BASE_PATH")

    sqlite_pool_size: int = 5  # SQLITE_POOL_SIZE
    sqlite_pool_max_overflow: int = 10  # SQLITE_POOL_MAX_OVERFLOW (burst headroom for parallel E2E)
    sqlite_busy_timeout_ms: int = (
        30000  # SQLITE_BUSY_TIMEOUT_MS (boosted to 30s to eliminate locked storms under concurrent writes)
    )
    database_echo: bool = False  # DATABASE_ECHO
    database_url: str = ""  # DATABASE_URL (optional AGE graph store; default SQLite graph)
    checkpointer_mode: str = ""  # CHECKPOINTER_MODE (memory|sqlite; empty = sqlite)

    @field_validator("checkpointer_mode")
    @classmethod
    def _validate_checkpointer_mode(cls, v: str) -> str:
        normalized = v.strip().lower()
        if normalized not in {"", "memory", "sqlite"}:
            raise ValueError(
                f"CHECKPOINTER_MODE must be empty, 'memory', or 'sqlite'; got {v!r}. "
                "PostgreSQL checkpoint is not supported; use SQLite on the persistent volume."
            )
        return normalized

    @staticmethod
    def _resolve(current: str, base: Path, default_subdir: str) -> str:
        """Resolve a path field: use *base / default_subdir* when empty, else expand the user-supplied value."""
        if not current:
            return str(base / default_subdir)
        return str(Path(current).expanduser().resolve())

    @model_validator(mode="after")
    def resolve_paths(self) -> "DatabaseSettings":
        base = Path(self.state_dir).expanduser().resolve()
        self.state_dir = str(base)

        self.sqlite_path = self._resolve(self.sqlite_path, base, "data.db")
        self.qdrant_path = self._resolve(self.qdrant_path, base, "qdrant")
        self.sqlite_db_path = self._resolve(self.sqlite_db_path, base, "checkpoints.db")
        self.harness_dir = self._resolve(self.harness_dir, base, "harness")
        self.event_log_dir = self._resolve(self.event_log_dir, base, "event_logs")
        self.memory_base_path = self._resolve(self.memory_base_path, base, "memory")

        return self

    @field_validator("sqlite_pool_size")
    @classmethod
    def _clamp_pool_size(cls, v: int) -> int:
        return max(1, min(64, v))

    @field_validator("sqlite_pool_max_overflow")
    @classmethod
    def _clamp_pool_max_overflow(cls, v: int) -> int:
        return max(0, min(64, v))

    @field_validator("sqlite_busy_timeout_ms")
    @classmethod
    def _clamp_busy_timeout(cls, v: int) -> int:
        return max(0, min(60000, v))


class ServiceSettings(BaseSettings):
    """Non-LLM server integrations (not user business config)."""

    model_config = SettingsConfigDict(env_prefix="")

    github_token: SecretStr = SecretStr("")  # GITHUB_TOKEN (skill discovery, security dashboard)
    cron_failure_webhook_url: str = ""  # CRON_FAILURE_WEBHOOK_URL


class ControlPlaneSettings(BaseSettings):
    """Sandbox control-plane connectivity ([S] only). Loaded once at boot into settings."""

    model_config = SettingsConfigDict(env_prefix="")

    url: str = Field(default="", validation_alias="CONTROL_PLANE_URL")
    telemetry_token: SecretStr = Field(default=SecretStr(""), validation_alias="CONTROL_PLANE_TELEMETRY_TOKEN")
    telemetry_subject: str = Field(default="", validation_alias="CONTROL_PLANE_TELEMETRY_SUBJECT")
    sandbox_id: str = Field(default="", validation_alias="SANDBOX_ID")
    platform_wu_per_usd: float = Field(default=1000.0, validation_alias="PLATFORM_WU_PER_USD")

    def effective_url(self, *, dev_fallback: str = "http://localhost:8001") -> str:
        normalized = self.url.strip().rstrip("/")
        return normalized or dev_fallback


class ContextCompactionTelemetrySettings(BaseSettings):
    """[S] Context compaction telemetry batching tunables."""

    model_config = SettingsConfigDict(env_prefix="CONTEXT_COMPACTION_TELEMETRY_")

    batch_size: int = 16
    flush_interval_seconds: float = 2.0
    queue_size: int = 256


class MemoryBriefStatusTelemetrySettings(BaseSettings):
    """[S] Memory brief status telemetry batching tunables."""

    model_config = SettingsConfigDict(env_prefix="MEMORY_BRIEF_STATUS_TELEMETRY_")

    batch_size: int = 32
    flush_interval_seconds: float = 3.0
    queue_size: int = 512
    allowed_phases: str = "stream,persist"


class ExecutionCacheSettings(BaseSettings):
    """[O] Chat agent execution unit cache & idle reclaim settings."""

    model_config = SettingsConfigDict(env_prefix="EXECUTION_CACHE_")

    idle_reclaim_timeout_seconds: float = Field(
        default=1800.0,
        validation_alias="MYRM_EXECUTION_CACHE_IDLE_SECONDS",
        description="[O] Idle timeout before cached agent execution units and heavy resources are reclaimed (0 = disable auto-reclaim)",
    )
    max_reaper_interval_seconds: float = 60.0


class MemoryGuardianGuardTelemetrySettings(BaseSettings):
    """[S] Guardian guard-unavailable telemetry batching tunables."""

    model_config = SettingsConfigDict(env_prefix="MEMORY_GUARDIAN_GUARD_TELEMETRY_")

    batch_size: int = 24
    flush_interval_seconds: float = 3.0
    queue_size: int = 256
