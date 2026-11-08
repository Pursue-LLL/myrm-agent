"""[INPUT]
- .channels / .infra / .llm / .security (POS: settings groups composed into AppSettings)
- pydantic_settings (POS: env and dotenv sources)

[OUTPUT]
- _AppSettingsEnvSource, _AppSettingsDotEnvSource, AppSettings

[POS]
Application settings: the composed AppSettings and its env/dotenv sources.
"""

from __future__ import annotations

from pydantic import Field, SecretStr, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from .channels import (
    BrowserPoolSettings,
    DingTalkChannelSettings,
    McpSettings,
    WebUISettings,
)
from .infra import (
    ContextCompactionTelemetrySettings,
    ControlPlaneSettings,
    DatabaseSettings,
    ExecutionCacheSettings,
    MemoryBriefStatusTelemetrySettings,
    MemoryGuardianGuardTelemetrySettings,
    MessageFilterSettings,
    MonitoringSettings,
    ServiceSettings,
)
from .llm import (
    PROVIDER_CACHE_CONFIGS,
    CacheSettings,
    LLMProvider,
    ProviderCacheConfig,
)
from .security import (
    AgentGatewaySettings,
    BashAuditSettings,
    CodeExecutionSettings,
    SecuritySettings,
)


class _AppSettingsEnvSource(EnvSettingsSource):
    """Env source that ignores nested BaseSettings fields to prevent raw env var collisions (e.g. AGENT=1)."""

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[object, str, bool]:
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseSettings):
            return None, field_name, False
        return super().get_field_value(field, field_name)


class _AppSettingsDotEnvSource(DotEnvSettingsSource):
    """DotEnv source that ignores nested BaseSettings fields to prevent raw env var collisions."""

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[object, str, bool]:
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseSettings):
            return None, field_name, False
        return super().get_field_value(field, field_name)


class AppSettings(BaseSettings):
    """Root settings — loads `.env` ([P]/[O] only; see `.env.example`)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            _AppSettingsEnvSource(settings_cls),
            _AppSettingsDotEnvSource(
                settings_cls,
                env_file=cls.model_config.get("env_file"),
                env_file_encoding=cls.model_config.get("env_file_encoding"),
            ),
            file_secret_settings,
        )

    # --- [P] HTTP listen ---
    port: int = 8080  # PORT
    host: str = "0.0.0.0"  # HOST

    # --- Code constants (not env-overridable in .env.example) ---
    app_name: str = "MyrmAgent"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"

    # --- [O] CORS ---
    cors_origins: str = ""  # CORS_ORIGINS (comma-separated)

    # --- [O] Public base URL (absolute channel-notification deep links) ---
    app_base_url: str = Field(
        default="",
        validation_alias="APP_BASE_URL",
        description="[O] Public web URL (no trailing slash) for clickable links in IM notifications; empty keeps relative paths",
    )

    # --- [P] Deploy paths ---
    project_dir: str = Field(default=".", validation_alias="MYRM_PROJECT_DIR")
    cp_public_ingress_url: str = Field(
        default="",
        validation_alias="CP_PUBLIC_INGRESS_URL",
        description="[S] Control-plane public ingress URL",
    )

    # --- [S] Sandbox secrets ---
    sandbox_api_key: SecretStr = SecretStr("")  # SANDBOX_API_KEY
    config_encryption_key: SecretStr = SecretStr("")  # CONFIG_ENCRYPTION_KEY
    internal_service_key: SecretStr = SecretStr("")  # INTERNAL_SERVICE_KEY

    # --- [O] Auth CAPTCHA ---
    hcaptcha_secret_key: SecretStr = SecretStr("")  # HCAPTCHA_SECRET_KEY

    # --- [O] Memory Command Center + experimental memory HTTP surface ---
    memory_labs_enabled: bool = Field(
        default=False,
        validation_alias="MYRM_MEMORY_LABS",
        description=(
            "[O] Mount the /memory/command-center* routes (except graph and evidence/playback, which are always mounted) "
            "and every other memory route that only the Labs panels call (see app/api/memory/router.py)"
        ),
    )

    # --- [O] Browser extension bridge ---
    extension_auth_token: SecretStr = SecretStr("")  # EXTENSION_AUTH_TOKEN

    # --- [O] Auth audit log rotation ---
    auth_audit_log_max_size_mb: int = 10  # AUTH_AUDIT_LOG_MAX_SIZE_MB
    auth_audit_log_max_age_days: int = 7  # AUTH_AUDIT_LOG_MAX_AGE_DAYS
    auth_audit_log_retention_days: int = 30  # AUTH_AUDIT_LOG_RETENTION_DAYS
    auth_audit_log_compress: bool = True  # AUTH_AUDIT_LOG_COMPRESS

    # --- [O] Harness event log line limit ---
    event_log_max_jsonl_line_bytes: int = 100 * 1024  # EVENT_LOG_MAX_JSONL_LINE_BYTES

    # --- [O] Google Workspace OAuth (GUI integration connect flow) ---
    google_client_id: str = Field(default="", validation_alias="GOOGLE_CLIENT_ID")
    google_client_secret: SecretStr = Field(default=SecretStr(""), validation_alias="GOOGLE_CLIENT_SECRET")

    # --- Grouped sub-settings (see classes above for env var names) ---
    cache: CacheSettings = Field(default_factory=CacheSettings)
    message_filter: MessageFilterSettings = Field(default_factory=MessageFilterSettings)
    bash_audit: BashAuditSettings = Field(default_factory=BashAuditSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    channel_dingtalk: DingTalkChannelSettings = Field(default_factory=DingTalkChannelSettings)
    mcp: McpSettings = Field(default_factory=McpSettings)
    browser_pool: BrowserPoolSettings = Field(default_factory=BrowserPoolSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    code_execution: CodeExecutionSettings = Field(default_factory=CodeExecutionSettings)
    agent: AgentGatewaySettings = Field(default_factory=AgentGatewaySettings)
    webui: WebUISettings = Field(default_factory=WebUISettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    services: ServiceSettings = Field(default_factory=ServiceSettings)
    control_plane: ControlPlaneSettings = Field(default_factory=ControlPlaneSettings)
    context_compaction_telemetry: ContextCompactionTelemetrySettings = Field(default_factory=ContextCompactionTelemetrySettings)
    memory_brief_status_telemetry: MemoryBriefStatusTelemetrySettings = Field(default_factory=MemoryBriefStatusTelemetrySettings)
    memory_guardian_guard_telemetry: MemoryGuardianGuardTelemetrySettings = Field(
        default_factory=MemoryGuardianGuardTelemetrySettings
    )
    execution_cache: ExecutionCacheSettings = Field(default_factory=ExecutionCacheSettings)

    @field_validator("port")
    @classmethod
    def _validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError(f"port must be 1-65535, got {v}")
        return v

    @field_validator("event_log_max_jsonl_line_bytes")
    @classmethod
    def _validate_event_log_line_max(cls, v: int) -> int:
        if v < 64:
            raise ValueError("event_log_max_jsonl_line_bytes must be >= 64")
        if v > 10 * 1024 * 1024:
            raise ValueError("event_log_max_jsonl_line_bytes unreasonably large (max 10 MiB)")
        return v

    # --- Provider helpers ---

    def get_provider(self, model: str) -> LLMProvider:
        """识别 LLM 提供商"""
        m = model.lower()
        if any(s in m for s in ("openai", "gpt-")):
            return LLMProvider.OPENAI
        if any(s in m for s in ("anthropic", "claude")):
            return LLMProvider.ANTHROPIC
        if "deepseek" in m:
            return LLMProvider.DEEPSEEK
        if any(s in m for s in ("google", "gemini")):
            return LLMProvider.GOOGLE
        if any(s in m for s in ("zhipu", "glm-")):
            return LLMProvider.ZHIPU
        if "yunshu" in m:
            return LLMProvider.YUNSHU
        if "xiaomi_mimo" in m:
            return LLMProvider.XIAOMI
        return LLMProvider.OTHER

    def get_provider_cache_config(self, model: str) -> ProviderCacheConfig:
        """获取特定模型的缓存配置"""
        provider = self.get_provider(model)
        return PROVIDER_CACHE_CONFIGS.get(provider, PROVIDER_CACHE_CONFIGS[LLMProvider.OTHER])

    def validate_for_sandbox(self) -> None:
        """Sandbox 模式启动前校验，缺少必要配置时立即抛出 RuntimeError。"""
        missing: list[str] = []
        if not self.sandbox_api_key.get_secret_value():
            missing.append("SANDBOX_API_KEY")
        if not self.config_encryption_key.get_secret_value():
            missing.append("CONFIG_ENCRYPTION_KEY")
        if missing:
            raise RuntimeError(f"Sandbox mode requires: {', '.join(missing)}")

    def config_summary(self) -> dict[str, object]:
        """Redacted config snapshot for startup logs."""
        return {
            "port": self.port,
            "host": self.host,
            "mcp.allow_stdio": self.mcp.allow_stdio,
            "mcp.require_https": self.mcp.require_https,
            "event_log.max_jsonl_line_bytes": self.event_log_max_jsonl_line_bytes,
            "agent.max_concurrent": self.agent.max_concurrent,
            "database.sqlite_path": self.database.sqlite_path,
            "cp_public_ingress_url": self.cp_public_ingress_url or "(not set)",
            "sandbox_api_key": ("***" if self.sandbox_api_key.get_secret_value() else "(not set)"),
            "config_encryption_key": ("***" if self.config_encryption_key.get_secret_value() else "(not set)"),
        }
