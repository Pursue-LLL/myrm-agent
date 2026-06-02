"""AppSettings 配置中心测试

覆盖场景:
- C1: 默认值加载
- C2: 环境变量 override
- C3: validate_for_sandbox() 校验
- C4: SecretStr 字段
- C5: field_validator (port / pool_size / busy_timeout)
- C6: config_summary() 脱敏
- C7: RateLimitSettings.register_limit validation_alias
- C8: LLMProvider / get_provider / get_provider_cache_config
- C9: 嵌套子配置独立性
"""

import os

import pytest

from app.config.settings import (
    PROVIDER_CACHE_CONFIGS,
    AppSettings,
    DatabaseSettings,
    LLMProvider,
    McpSettings,
    RateLimitSettings,
    WebUISettings,
)


def _make_settings(**overrides: str) -> AppSettings:
    """创建隔离的 AppSettings 实例。

    对于根级字段（port, sandbox_api_key 等），通过环境变量覆盖。
    注意: 嵌套子配置在类定义时已构造默认实例，运行时环境变量无法影响。
    需要测试子配置环境变量时，应直接构造对应的子配置类。
    """
    old_env: dict[str, str | None] = {}
    for k, v in overrides.items():
        old_env[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        return AppSettings()
    finally:
        for k, old_v in old_env.items():
            if old_v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old_v


# ---------------------------------------------------------------------------
# C1: 默认值加载
# ---------------------------------------------------------------------------


class TestDefaultValues:
    def test_root_defaults(self) -> None:
        s = _make_settings()
        assert s.port == 8080
        assert s.host == "0.0.0.0"
        assert s.app_name == "MyrmAgent"
        assert s.api_prefix == "/api/v1"
        assert s.browser_auto_warmup is False

    def test_mcp_defaults(self) -> None:
        s = _make_settings()
        assert s.mcp.allow_stdio is True
        assert s.mcp.require_https is True
        assert s.mcp.max_response_size == 10 * 1024 * 1024

    def test_rate_limit_defaults(self) -> None:
        s = _make_settings()
        assert s.rate_limit.chat == "30/minute;500/hour"
        assert s.rate_limit.register_limit == "3/hour"
        assert s.rate_limit.webhook == "60/minute;300/hour"

    def test_agent_gateway_defaults(self) -> None:
        s = _make_settings()
        assert s.agent.max_concurrent == 20
        assert s.agent.max_per_user == 3
        assert s.agent.queue_timeout == 10.0

    def test_database_defaults(self) -> None:
        s = _make_settings()
        assert s.database.sqlite_pool_size == 5
        assert s.database.sqlite_busy_timeout_ms == 3000

    def test_database_path_defaults_derive_from_state_dir(self) -> None:
        db = DatabaseSettings()
        from pathlib import Path
        base = Path(db.state_dir)
        assert db.sqlite_path == str(base / "data.db")
        assert db.qdrant_path == str(base / "qdrant")
        assert db.sqlite_db_path == str(base / "checkpoints.db")
        assert db.harness_dir == str(base / "harness")
        assert db.event_log_dir == str(base / "event_logs")
        assert db.memory_base_path == str(base / "memory")


# ---------------------------------------------------------------------------
# C2: 环境变量 override
# ---------------------------------------------------------------------------


class TestEnvOverride:
    def test_root_port_override(self) -> None:
        s = _make_settings(PORT="9090")
        assert s.port == 9090

    def test_mcp_prefix_override(self) -> None:
        old = os.environ.get("MCP_ALLOW_STDIO")
        os.environ["MCP_ALLOW_STDIO"] = "false"
        try:
            mcp = McpSettings()
            assert mcp.allow_stdio is False
        finally:
            if old is None:
                os.environ.pop("MCP_ALLOW_STDIO", None)
            else:
                os.environ["MCP_ALLOW_STDIO"] = old

    def test_agent_prefix_override(self) -> None:
        from app.config.settings import AgentGatewaySettings

        old = os.environ.get("AGENT_MAX_CONCURRENT")
        os.environ["AGENT_MAX_CONCURRENT"] = "50"
        try:
            ag = AgentGatewaySettings()
            assert ag.max_concurrent == 50
        finally:
            if old is None:
                os.environ.pop("AGENT_MAX_CONCURRENT", None)
            else:
                os.environ["AGENT_MAX_CONCURRENT"] = old

    def test_webui_prefix_override(self) -> None:
        old = os.environ.get("WEBUI_PORT")
        os.environ["WEBUI_PORT"] = "30000"
        try:
            webui = WebUISettings()
            assert webui.port == 30000
        finally:
            if old is None:
                os.environ.pop("WEBUI_PORT", None)
            else:
                os.environ["WEBUI_PORT"] = old

    def test_browser_pool_prefix_override(self) -> None:
        from app.config.settings import BrowserPoolSettings

        old = os.environ.get("GLOBAL_BROWSER_POOL_MAX_BROWSERS")
        os.environ["GLOBAL_BROWSER_POOL_MAX_BROWSERS"] = "10"
        try:
            bp = BrowserPoolSettings()
            assert bp.max_browsers == 10
        finally:
            if old is None:
                os.environ.pop("GLOBAL_BROWSER_POOL_MAX_BROWSERS", None)
            else:
                os.environ["GLOBAL_BROWSER_POOL_MAX_BROWSERS"] = old


# ---------------------------------------------------------------------------
# C2b: DatabaseSettings path override via env / direct arg
# ---------------------------------------------------------------------------


class TestDatabasePathOverrides:
    def test_event_log_dir_env_override(self) -> None:
        old = os.environ.get("EVENT_LOG_DIR")
        os.environ["EVENT_LOG_DIR"] = "/tmp/custom_events"
        try:
            db = DatabaseSettings()
            assert db.event_log_dir == "/private/tmp/custom_events" or db.event_log_dir == "/tmp/custom_events"
        finally:
            if old is None:
                os.environ.pop("EVENT_LOG_DIR", None)
            else:
                os.environ["EVENT_LOG_DIR"] = old

    def test_memory_base_path_env_override(self) -> None:
        old = os.environ.get("MEMORY_BASE_PATH")
        os.environ["MEMORY_BASE_PATH"] = "/tmp/custom_memory"
        try:
            db = DatabaseSettings()
            assert db.memory_base_path == "/private/tmp/custom_memory" or db.memory_base_path == "/tmp/custom_memory"
        finally:
            if old is None:
                os.environ.pop("MEMORY_BASE_PATH", None)
            else:
                os.environ["MEMORY_BASE_PATH"] = old

    def test_custom_state_dir_propagates(self) -> None:
        from pathlib import Path
        old = os.environ.get("MYRM_DATA_DIR")
        os.environ["MYRM_DATA_DIR"] = "/tmp/test-workspace"
        try:
            db = DatabaseSettings()
            base = Path(db.state_dir)
            assert db.event_log_dir == str(base / "event_logs")
            assert db.memory_base_path == str(base / "memory")
            assert db.sqlite_path == str(base / "data.db")
        finally:
            if old is None:
                os.environ.pop("MYRM_DATA_DIR", None)
            else:
                os.environ["MYRM_DATA_DIR"] = old

    def test_explicit_path_overrides_default(self) -> None:
        old_log = os.environ.get("EVENT_LOG_DIR")
        old_mem = os.environ.get("MEMORY_BASE_PATH")
        os.environ["EVENT_LOG_DIR"] = "/explicit/logs"
        os.environ["MEMORY_BASE_PATH"] = "/explicit/mem"
        try:
            db = DatabaseSettings()
            assert "/explicit/logs" in db.event_log_dir
            assert "/explicit/mem" in db.memory_base_path
        finally:
            if old_log is None:
                os.environ.pop("EVENT_LOG_DIR", None)
            else:
                os.environ["EVENT_LOG_DIR"] = old_log
            if old_mem is None:
                os.environ.pop("MEMORY_BASE_PATH", None)
            else:
                os.environ["MEMORY_BASE_PATH"] = old_mem


# ---------------------------------------------------------------------------
# C3: validate_for_sandbox()
# ---------------------------------------------------------------------------


class TestSandboxValidation:
    def test_missing_sandbox_api_key(self) -> None:
        s = _make_settings()
        with pytest.raises(RuntimeError, match="SANDBOX_API_KEY"):
            s.validate_for_sandbox()

    def test_missing_encryption_key(self) -> None:
        s = _make_settings(SANDBOX_API_KEY="test-secret")
        with pytest.raises(RuntimeError, match="CONFIG_ENCRYPTION_KEY"):
            s.validate_for_sandbox()

    def test_missing_database_url_for_postgres(self) -> None:
        from pydantic import SecretStr as _SecretStr

        s = AppSettings(
            sandbox_api_key=_SecretStr("test"),
            config_encryption_key=_SecretStr("test"),
            database=DatabaseSettings(checkpointer_mode="postgres", database_url=""),
        )
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            s.validate_for_sandbox()

    def test_all_present_passes(self) -> None:
        s = _make_settings(
            SANDBOX_API_KEY="test-key",
            CONFIG_ENCRYPTION_KEY="test-enc",
        )
        s.validate_for_sandbox()

    def test_postgres_with_url_passes(self) -> None:
        from pydantic import SecretStr as _SecretStr

        s = AppSettings(
            sandbox_api_key=_SecretStr("test"),
            config_encryption_key=_SecretStr("test"),
            database=DatabaseSettings(
                checkpointer_mode="postgres",
                database_url="postgresql://localhost/test",
            ),
        )
        s.validate_for_sandbox()


# ---------------------------------------------------------------------------
# C4: SecretStr 字段
# ---------------------------------------------------------------------------


class TestSecretStr:
    def test_sandbox_api_key_redacted_in_repr(self) -> None:
        s = _make_settings(SANDBOX_API_KEY="my-super-secret")
        assert "my-super-secret" not in repr(s)
        assert s.sandbox_api_key.get_secret_value() == "my-super-secret"

    def test_config_encryption_key_get_value(self) -> None:
        s = _make_settings(CONFIG_ENCRYPTION_KEY="enc-key-123")
        assert s.config_encryption_key.get_secret_value() == "enc-key-123"

    def test_empty_secret_default(self) -> None:
        s = _make_settings()
        assert s.sandbox_api_key.get_secret_value() == ""
        assert s.internal_service_key.get_secret_value() == ""


# ---------------------------------------------------------------------------
# C5: field_validator
# ---------------------------------------------------------------------------


class TestFieldValidators:
    def test_port_valid_range(self) -> None:
        s = _make_settings(PORT="443")
        assert s.port == 443

    def test_port_below_range(self) -> None:
        with pytest.raises(ValueError, match="port must be 1-65535"):
            _make_settings(PORT="0")

    def test_port_above_range(self) -> None:
        with pytest.raises(ValueError, match="port must be 1-65535"):
            _make_settings(PORT="70000")

    def test_sqlite_pool_size_clamped_low(self) -> None:
        s = DatabaseSettings(sqlite_pool_size=-1)
        assert s.sqlite_pool_size == 1

    def test_sqlite_pool_size_clamped_high(self) -> None:
        s = DatabaseSettings(sqlite_pool_size=100)
        assert s.sqlite_pool_size == 32

    def test_busy_timeout_clamped(self) -> None:
        s = DatabaseSettings(sqlite_busy_timeout_ms=99999)
        assert s.sqlite_busy_timeout_ms == 60000


# ---------------------------------------------------------------------------
# C6: config_summary() 脱敏
# ---------------------------------------------------------------------------


class TestConfigSummary:
    def test_no_secret_leaked(self) -> None:
        s = _make_settings(SANDBOX_API_KEY="top-secret-value", CONFIG_ENCRYPTION_KEY="enc-key")
        summary = s.config_summary()
        assert summary["sandbox_api_key"] == "***"
        assert summary["config_encryption_key"] == "***"
        assert "top-secret-value" not in str(summary)

    def test_empty_secret_shows_not_set(self) -> None:
        s = _make_settings()
        summary = s.config_summary()
        assert summary["sandbox_api_key"] == "(not set)"
        assert summary["config_encryption_key"] == "(not set)"

    def test_contains_key_fields(self) -> None:
        s = _make_settings()
        summary = s.config_summary()
        assert "port" in summary
        assert "host" in summary
        assert "agent.max_concurrent" in summary
        assert "cp_public_ingress_url" in summary


# ---------------------------------------------------------------------------
# C7: RateLimitSettings validation_alias
# ---------------------------------------------------------------------------


class TestRateLimitAlias:
    def test_register_alias_from_env(self) -> None:
        old = os.environ.get("RATE_LIMIT_REGISTER")
        os.environ["RATE_LIMIT_REGISTER"] = "10/hour"
        try:
            rl = RateLimitSettings()
            assert rl.register_limit == "10/hour"
        finally:
            if old is None:
                os.environ.pop("RATE_LIMIT_REGISTER", None)
            else:
                os.environ["RATE_LIMIT_REGISTER"] = old

    def test_register_default(self) -> None:
        rl = RateLimitSettings()
        assert rl.register_limit == "3/hour"


# ---------------------------------------------------------------------------
# C8: LLMProvider helpers
# ---------------------------------------------------------------------------


class TestLLMProvider:
    @pytest.mark.parametrize(
        "model,expected",
        [
            ("gpt-4o", LLMProvider.OPENAI),
            ("openai/gpt-4", LLMProvider.OPENAI),
            ("claude-3-sonnet", LLMProvider.ANTHROPIC),
            ("anthropic/claude-3", LLMProvider.ANTHROPIC),
            ("deepseek-chat", LLMProvider.DEEPSEEK),
            ("google/gemini-pro", LLMProvider.GOOGLE),
            ("gemini-2.0-flash", LLMProvider.GOOGLE),
            ("glm-4", LLMProvider.ZHIPU),
            ("yunshu/model-x", LLMProvider.YUNSHU),
            ("unknown-model", LLMProvider.OTHER),
        ],
    )
    def test_get_provider(self, model: str, expected: LLMProvider) -> None:
        s = _make_settings()
        assert s.get_provider(model) == expected

    def test_get_provider_cache_config(self) -> None:
        s = _make_settings()
        config = s.get_provider_cache_config("claude-3-sonnet")
        assert config.cache_type == "hybrid"
        assert config.discount_rate == 0.1

    def test_provider_cache_config_fallback(self) -> None:
        s = _make_settings()
        config = s.get_provider_cache_config("random-unknown-model")
        assert config == PROVIDER_CACHE_CONFIGS[LLMProvider.OTHER]


# ---------------------------------------------------------------------------
# C9: 子配置独立性
# ---------------------------------------------------------------------------


class TestSubConfigIsolation:
    def test_mcp_independent(self) -> None:
        mcp = McpSettings()
        assert mcp.allow_stdio is True

    def test_webui_independent(self) -> None:
        webui = WebUISettings()
        assert webui.port == 25808

    def test_rate_limit_independent(self) -> None:
        rl = RateLimitSettings()
        assert rl.chat == "30/minute;500/hour"
