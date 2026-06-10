"""统一配置中心

所有应用配置的单一事实源。基于 pydantic-settings，自动从环境变量和 .env 文件加载。

使用方式：
    from app.config.settings import settings

    settings.port                    # HTTP listen port
    settings.database.state_dir      # Workspace root (~/.myrm)
    settings.sandbox_api_key.get_secret_value()  # [S] sandbox only

环境变量覆盖：
    仅进程级 [P] 与运维级 [O] 字段可通过环境变量覆盖（完整清单见 .env.example AppSettings index）。
    LLM / Embedding / Search 等业务配置必须在 WebUI Settings（DB）或 harness 实例注入中配置。
    [S] 见 .env.sandbox.example；[T] 见 .env.test.example（pytest only）。
    子配置使用各自的 env_prefix（如 RATE_LIMIT_*, MCP_* 等）。
"""

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# LLM Provider cache configs
# ---------------------------------------------------------------------------


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    GOOGLE = "google"
    ZHIPU = "zhipu"
    YUNSHU = "yunshu"
    XIAOMI = "xiaomi"
    OTHER = "other"


class ProviderCacheConfig:
    """Per-provider prompt cache configuration.

    Attributes:
        cache_type: auto (prefix-based), explicit (cache_control), hybrid.
        discount_rate: Cache hit discount (0.1 = 90% off).
        min_cache_tokens: Minimum tokens for caching.
        ttl_minutes: Cache TTL.
        write_cost_multiplier: Extra write cost (1.0 = none).
    """

    __slots__ = (
        "cache_type",
        "discount_rate",
        "min_cache_tokens",
        "ttl_minutes",
        "write_cost_multiplier",
    )

    def __init__(
        self,
        cache_type: Literal["auto", "explicit", "hybrid"],
        discount_rate: float,
        min_cache_tokens: int,
        ttl_minutes: int,
        write_cost_multiplier: float = 1.0,
    ) -> None:
        self.cache_type = cache_type
        self.discount_rate = discount_rate
        self.min_cache_tokens = min_cache_tokens
        self.ttl_minutes = ttl_minutes
        self.write_cost_multiplier = write_cost_multiplier


PROVIDER_CACHE_CONFIGS: dict[LLMProvider, ProviderCacheConfig] = {
    LLMProvider.ANTHROPIC: ProviderCacheConfig("hybrid", 0.1, 1024, 5, 1.25),
    LLMProvider.OPENAI: ProviderCacheConfig("auto", 0.5, 1024, 10),
    LLMProvider.GOOGLE: ProviderCacheConfig("hybrid", 0.25, 1024, 60),
    LLMProvider.DEEPSEEK: ProviderCacheConfig("auto", 0.1, 64, 30),
    LLMProvider.ZHIPU: ProviderCacheConfig("auto", 0.5, 1024, 10),
    LLMProvider.YUNSHU: ProviderCacheConfig("auto", 0.5, 1024, 10),
    LLMProvider.XIAOMI: ProviderCacheConfig("auto", 0.5, 1024, 10),
    LLMProvider.OTHER: ProviderCacheConfig("auto", 0.5, 1024, 10),
}

# =============================================================================
# Tier legend (env vars only — business config lives in WebUI DB)
#   [P] Process  — server boot / paths / listen
#   [O] Ops        — operational toggles, limits, integrations
#   [S] Sandbox    — DEPLOY_MODE=sandbox only (see .env.sandbox.example)
# =============================================================================

# ---------------------------------------------------------------------------
# [O] Feature toggles — env: ENABLE_PROMPT_CACHING, ENABLE_BATCH_CLEANUP
# ---------------------------------------------------------------------------


class CacheSettings(BaseSettings):
    """Harness-level cache optimization toggles."""

    model_config = SettingsConfigDict(env_prefix="ENABLE_")

    prompt_caching: bool = True  # ENABLE_PROMPT_CACHING
    batch_cleanup: bool = True  # ENABLE_BATCH_CLEANUP


# ---------------------------------------------------------------------------
# [O] Chat message filter — env: MESSAGE_FILTER_ENABLED, ADMIN_API_KEYS
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# [O] Bash audit alerting — env: BASH_AUDIT_WEBHOOK_URL, BASH_AUDIT_SLACK_WEBHOOK
# ---------------------------------------------------------------------------


class BashAuditSettings(BaseSettings):
    """Outbound webhooks for bash audit anomaly alerts."""

    model_config = SettingsConfigDict(env_prefix="BASH_AUDIT_")

    webhook_url: str = ""  # BASH_AUDIT_WEBHOOK_URL
    slack_webhook: str = ""  # BASH_AUDIT_SLACK_WEBHOOK


# ---------------------------------------------------------------------------
# [O] Observability — env: METRICS_ENABLED, OTEL_*
# ---------------------------------------------------------------------------


class MonitoringSettings(BaseSettings):
    """Prometheus metrics and OpenTelemetry tracing toggles."""

    model_config = SettingsConfigDict(env_prefix="")

    metrics_enabled: bool = Field(default=False, validation_alias="METRICS_ENABLED")
    otel_enabled: bool = Field(default=False, validation_alias="OTEL_ENABLED")
    otel_exporter_otlp_endpoint: str = Field(
        default="",
        validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    otel_sample_rate: float = Field(default=0.1, validation_alias="OTEL_SAMPLE_RATE")


# ---------------------------------------------------------------------------
# [O] DingTalk HTTP client — env prefix: CHANNEL_DINGTALK_
# ---------------------------------------------------------------------------


class DingTalkChannelSettings(BaseSettings):
    """DingTalk channel API HTTP timeouts (seconds)."""

    model_config = SettingsConfigDict(env_prefix="CHANNEL_DINGTALK_")

    timeout: float = 15.0  # CHANNEL_DINGTALK_TIMEOUT
    media_timeout: float = 30.0  # CHANNEL_DINGTALK_MEDIA_TIMEOUT
    download_timeout: float = 60.0  # CHANNEL_DINGTALK_DOWNLOAD_TIMEOUT


# ---------------------------------------------------------------------------
# [O] MCP security — env prefix: MCP_
# ---------------------------------------------------------------------------


class McpSettings(BaseSettings):
    """MCP transport and SSRF protection policy."""

    model_config = SettingsConfigDict(env_prefix="MCP_")

    allow_stdio: bool = True  # MCP_ALLOW_STDIO
    require_https: bool = True  # MCP_REQUIRE_HTTPS
    enable_ssrf_protection: bool = True  # MCP_ENABLE_SSRF_PROTECTION
    verify_timeout: int = 10  # MCP_VERIFY_TIMEOUT (seconds)
    max_response_size: int = 10 * 1024 * 1024  # MCP_MAX_RESPONSE_SIZE (bytes)


# ---------------------------------------------------------------------------
# [O] Rate limits — env prefix: RATE_LIMIT_
# ---------------------------------------------------------------------------


class RateLimitSettings(BaseSettings):
    """SlowAPI rate-limit rules (semicolon-separated windows)."""

    model_config = SettingsConfigDict(env_prefix="RATE_LIMIT_", populate_by_name=True)

    mcp_verify: str = "10/minute;100/hour"  # RATE_LIMIT_MCP_VERIFY
    chat: str = "30/minute;500/hour"  # RATE_LIMIT_CHAT
    file_upload: str = "10/hour"  # RATE_LIMIT_FILE_UPLOAD
    login: str = "5/minute;20/hour"  # RATE_LIMIT_LOGIN
    register_limit: str = Field(
        default="3/hour",
        validation_alias="RATE_LIMIT_REGISTER",
    )
    webhook: str = "60/minute;300/hour"  # RATE_LIMIT_WEBHOOK
    artifact_deploy: str = "20/hour"  # RATE_LIMIT_ARTIFACT_DEPLOY


# ---------------------------------------------------------------------------
# [O] Browser pool — env prefix: GLOBAL_BROWSER_POOL_
# ---------------------------------------------------------------------------


class BrowserPoolSettings(BaseSettings):
    """Playwright browser pool sizing (auto-tuned by DEPLOY_MODE)."""

    model_config = SettingsConfigDict(env_prefix="GLOBAL_BROWSER_POOL_")

    max_browsers: int = 5  # GLOBAL_BROWSER_POOL_MAX_BROWSERS
    warmup_browsers: int = 2  # GLOBAL_BROWSER_POOL_WARMUP_BROWSERS
    warmup_pages: int = 5  # GLOBAL_BROWSER_POOL_WARMUP_PAGES

    @model_validator(mode="after")
    def adapt_to_deploy_mode(self) -> "BrowserPoolSettings":
        """根据 DEPLOY_MODE 自动调整浏览器池配置，优化内存占用。

        - tauri (桌面端): 单用户场景，无需预热，max_browsers=1
        - webui (本地Web): 单用户场景，无需预热，max_browsers=2 (支持少量并发)
        - sandbox (SaaS): 多用户场景，保留默认预热配置
        """
        from app.config.deploy_mode import DeployMode, get_deploy_mode

        deploy_mode = get_deploy_mode()

        if deploy_mode == DeployMode.TAURI:
            if self.warmup_browsers == 2:
                self.warmup_browsers = 0
            if self.max_browsers == 5:
                self.max_browsers = 1
        elif deploy_mode in (DeployMode.LOCAL,):
            if self.warmup_browsers == 2:
                self.warmup_browsers = 0
            if self.max_browsers == 5:
                self.max_browsers = 2

        return self


# ---------------------------------------------------------------------------
# [O] Code execution policy — env prefix: CODE_EXECUTION_
# ---------------------------------------------------------------------------


class CodeExecutionSettings(BaseSettings):
    """Global code-execution network policy injected into harness at boot."""

    model_config = SettingsConfigDict(env_prefix="CODE_EXECUTION_")

    allow_network: bool = True  # CODE_EXECUTION_ALLOW_NETWORK
    allowed_hosts: str = ""  # CODE_EXECUTION_ALLOWED_HOSTS (comma-separated)


# ---------------------------------------------------------------------------
# [O] API security — env prefix: SECURITY_
# ---------------------------------------------------------------------------


class SecuritySettings(BaseSettings):
    """Request signature and SSO proxy authentication."""

    model_config = SettingsConfigDict(env_prefix="SECURITY_")

    signature_enabled: bool = False  # SECURITY_SIGNATURE_ENABLED
    timestamp_window: int = 60  # SECURITY_TIMESTAMP_WINDOW (seconds)
    nonce_ttl: int = 120  # SECURITY_NONCE_TTL (seconds)
    sso_proxy_enabled: bool = False  # SECURITY_SSO_PROXY_ENABLED
    sso_proxy_header: str = "Remote-User"  # SECURITY_SSO_PROXY_HEADER
    sso_proxy_trusted_ips: str = "127.0.0.1,::1"  # SECURITY_SSO_PROXY_TRUSTED_IPS


# ---------------------------------------------------------------------------
# [O] Agent gateway — env prefix: AGENT_
# ---------------------------------------------------------------------------


class AgentGatewaySettings(BaseSettings):
    """Concurrent agent execution limits and timeouts."""

    model_config = SettingsConfigDict(env_prefix="AGENT_")

    max_concurrent: int = 20  # AGENT_MAX_CONCURRENT
    max_per_user: int = 3  # AGENT_MAX_PER_USER
    queue_timeout: float = 10.0  # AGENT_QUEUE_TIMEOUT (seconds)
    execution_timeout: float = 300.0  # AGENT_EXECUTION_TIMEOUT (seconds)


# ---------------------------------------------------------------------------
# [O] WebUI sub-server — env prefix: WEBUI_
# ---------------------------------------------------------------------------


class WebUISettings(BaseSettings):
    """Embedded WebUI server (QR pairing, token issuance)."""

    model_config = SettingsConfigDict(env_prefix="WEBUI_")

    host: str = "127.0.0.1"  # WEBUI_HOST
    port: int = 25808  # WEBUI_PORT
    allow_remote: bool = False  # WEBUI_ALLOW_REMOTE
    token_expiry: int = 900  # WEBUI_TOKEN_EXPIRY (seconds)
    token_max_per_hour: int = 10  # WEBUI_TOKEN_MAX_PER_HOUR
    qrcode_size: int = 400  # WEBUI_QRCODE_SIZE (pixels)
    qrcode_border: int = 1  # WEBUI_QRCODE_BORDER (pixels)


# ---------------------------------------------------------------------------
# [P] Database & workspace paths
# ---------------------------------------------------------------------------


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
    sqlite_busy_timeout_ms: int = 3000  # SQLITE_BUSY_TIMEOUT_MS
    database_echo: bool = False  # DATABASE_ECHO
    database_url: str = ""  # DATABASE_URL (optional AGE graph store; default SQLite graph)
    qdrant_url: str = ""  # QDRANT_URL (remote vector store)
    qdrant_api_key: SecretStr = SecretStr("")  # QDRANT_API_KEY
    checkpointer_mode: str = ""  # CHECKPOINTER_MODE (memory|sqlite; empty = sqlite)

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
        return max(1, min(32, v))

    @field_validator("sqlite_busy_timeout_ms")
    @classmethod
    def _clamp_busy_timeout(cls, v: int) -> int:
        return max(0, min(60000, v))


# ---------------------------------------------------------------------------
# [S] Object storage (S3) — env: S3_*, AWS_*
# ---------------------------------------------------------------------------


class StorageSettings(BaseSettings):
    """S3-compatible object storage for sandbox artifact persistence."""

    model_config = SettingsConfigDict(env_prefix="")

    s3_endpoint_url: str = ""  # S3_ENDPOINT_URL
    s3_bucket_name: str = "myrm"  # S3_BUCKET_NAME
    s3_region: str = "auto"  # S3_REGION
    aws_access_key_id: SecretStr = SecretStr("")  # AWS_ACCESS_KEY_ID
    aws_secret_access_key: SecretStr = SecretStr("")  # AWS_SECRET_ACCESS_KEY


# ---------------------------------------------------------------------------
# [O] Server-side integrations — env: GITHUB_TOKEN, CRON_FAILURE_WEBHOOK_URL
# ---------------------------------------------------------------------------


class ServiceSettings(BaseSettings):
    """Non-LLM server integrations (not user business config)."""

    model_config = SettingsConfigDict(env_prefix="")

    github_token: SecretStr = SecretStr("")  # GITHUB_TOKEN (skill discovery, security dashboard)
    cron_failure_webhook_url: str = ""  # CRON_FAILURE_WEBHOOK_URL


# ---------------------------------------------------------------------------
# [S] Control plane — env: CONTROL_PLANE_*, TENANT_ID, SANDBOX_ID, TELEMETRY_*
# ---------------------------------------------------------------------------


class ControlPlaneSettings(BaseSettings):
    """Sandbox control-plane connectivity ([S] only). Loaded once at boot into settings."""

    model_config = SettingsConfigDict(env_prefix="")

    url: str = Field(default="", validation_alias="CONTROL_PLANE_URL")
    telemetry_token: SecretStr = Field(default="", validation_alias="CONTROL_PLANE_TELEMETRY_TOKEN")
    telemetry_subject: str = Field(default="", validation_alias="CONTROL_PLANE_TELEMETRY_SUBJECT")
    tenant_id: str = Field(default="default-tenant", validation_alias="TENANT_ID")
    sandbox_id: str = Field(default="", validation_alias="SANDBOX_ID")
    telemetry_push_interval: int = Field(default=3600, validation_alias="TELEMETRY_PUSH_INTERVAL")
    baseline_sync_interval: int = Field(default=86400, validation_alias="BASELINE_SYNC_INTERVAL")
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


# ---------------------------------------------------------------------------
# Root AppSettings
# ---------------------------------------------------------------------------


class AppSettings(BaseSettings):
    """Root settings — loads `.env` ([P]/[O] only; see `.env.example`)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
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
    skill_optimization_storage_type: str = Field(
        default="memory",
        validation_alias="SKILL_OPTIMIZATION_STORAGE_TYPE",
        description="[S] Skill optimization persistence: memory | sqlite",
    )

    # --- [O] Auth CAPTCHA ---
    hcaptcha_secret_key: SecretStr = SecretStr("")  # HCAPTCHA_SECRET_KEY

    # --- [O] Browser session warmup ---
    browser_auto_warmup: bool = False  # BROWSER_AUTO_WARMUP

    # --- [O] Browser extension bridge ---
    extension_auth_token: SecretStr = SecretStr("")  # EXTENSION_AUTH_TOKEN

    # --- [O] Auth audit log rotation ---
    auth_audit_log_max_size_mb: int = 10  # AUTH_AUDIT_LOG_MAX_SIZE_MB
    auth_audit_log_max_age_days: int = 7  # AUTH_AUDIT_LOG_MAX_AGE_DAYS
    auth_audit_log_retention_days: int = 30  # AUTH_AUDIT_LOG_RETENTION_DAYS
    auth_audit_log_compress: bool = True  # AUTH_AUDIT_LOG_COMPRESS

    # --- [O] Harness event log line limit ---
    event_log_max_jsonl_line_bytes: int = 100 * 1024  # EVENT_LOG_MAX_JSONL_LINE_BYTES

    # --- Grouped sub-settings (see classes above for env var names) ---
    cache: CacheSettings = CacheSettings()
    message_filter: MessageFilterSettings = MessageFilterSettings()
    bash_audit: BashAuditSettings = BashAuditSettings()
    monitoring: MonitoringSettings = MonitoringSettings()
    channel_dingtalk: DingTalkChannelSettings = DingTalkChannelSettings()
    mcp: McpSettings = McpSettings()
    rate_limit: RateLimitSettings = RateLimitSettings()
    browser_pool: BrowserPoolSettings = BrowserPoolSettings()
    security: SecuritySettings = SecuritySettings()
    code_execution: CodeExecutionSettings = CodeExecutionSettings()
    agent: AgentGatewaySettings = AgentGatewaySettings()
    webui: WebUISettings = WebUISettings()
    database: DatabaseSettings = DatabaseSettings()
    storage: StorageSettings = StorageSettings()
    services: ServiceSettings = ServiceSettings()
    control_plane: ControlPlaneSettings = ControlPlaneSettings()
    context_compaction_telemetry: ContextCompactionTelemetrySettings = ContextCompactionTelemetrySettings()

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
        if m.startswith(("openai/", "gpt-")):
            return LLMProvider.OPENAI
        if m.startswith(("anthropic/", "claude-")):
            return LLMProvider.ANTHROPIC
        if m.startswith(("deepseek/", "deepseek-")):
            return LLMProvider.DEEPSEEK
        if m.startswith(("google/", "gemini-")):
            return LLMProvider.GOOGLE
        if m.startswith(("zhipu/", "glm-")):
            return LLMProvider.ZHIPU
        if m.startswith("yunshu/"):
            return LLMProvider.YUNSHU
        if m.startswith("xiaomi_mimo/"):
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
            "browser_auto_warmup": self.browser_auto_warmup,
            "mcp.allow_stdio": self.mcp.allow_stdio,
            "mcp.require_https": self.mcp.require_https,
            "event_log.max_jsonl_line_bytes": self.event_log_max_jsonl_line_bytes,
            "agent.max_concurrent": self.agent.max_concurrent,
            "database.sqlite_path": self.database.sqlite_path,
            "cp_public_ingress_url": self.cp_public_ingress_url or "(not set)",
            "sandbox_api_key": ("***" if self.sandbox_api_key.get_secret_value() else "(not set)"),
            "config_encryption_key": ("***" if self.config_encryption_key.get_secret_value() else "(not set)"),
        }


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """获取全局配置实例（单例）"""
    return AppSettings()


settings = get_settings()

__all__ = [
    "AppSettings",
    "AgentGatewaySettings",
    "BrowserPoolSettings",
    "CacheSettings",
    "CodeExecutionSettings",
    "ContextCompactionTelemetrySettings",
    "ControlPlaneSettings",
    "DatabaseSettings",
    "LLMProvider",
    "McpSettings",
    "PROVIDER_CACHE_CONFIGS",
    "ProviderCacheConfig",
    "RateLimitSettings",
    "BashAuditSettings",
    "DingTalkChannelSettings",
    "MonitoringSettings",
    "MessageFilterSettings",
    "SecuritySettings",
    "ServiceSettings",
    "StorageSettings",
    "WebUISettings",
    "get_settings",
    "settings",
    "BASE_DIR",
]
