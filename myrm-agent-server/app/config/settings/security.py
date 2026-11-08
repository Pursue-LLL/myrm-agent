"""[INPUT]
- pydantic_settings (POS: env-backed settings base)

[OUTPUT]
- BashAuditSettings, CodeExecutionSettings, SecuritySettings, AgentGatewaySettings

[POS]
Application settings: bash audit, code execution, security and agent-gateway settings.
"""

from __future__ import annotations

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class BashAuditSettings(BaseSettings):
    """Outbound webhooks for bash audit anomaly alerts."""

    model_config = SettingsConfigDict(env_prefix="BASH_AUDIT_")

    webhook_url: str = ""  # BASH_AUDIT_WEBHOOK_URL
    slack_webhook: str = ""  # BASH_AUDIT_SLACK_WEBHOOK


class CodeExecutionSettings(BaseSettings):
    """Global code-execution network policy injected into harness at boot."""

    model_config = SettingsConfigDict(env_prefix="CODE_EXECUTION_")

    allow_network: bool = True  # CODE_EXECUTION_ALLOW_NETWORK
    allowed_hosts: str = ""  # CODE_EXECUTION_ALLOWED_HOSTS (comma-separated)


class SecuritySettings(BaseSettings):
    """Request signature and SSO proxy authentication."""

    model_config = SettingsConfigDict(env_prefix="SECURITY_")

    signature_enabled: bool = False  # SECURITY_SIGNATURE_ENABLED
    timestamp_window: int = 60  # SECURITY_TIMESTAMP_WINDOW (seconds)
    nonce_ttl: int = 120  # SECURITY_NONCE_TTL (seconds)
    sso_proxy_enabled: bool = False  # SECURITY_SSO_PROXY_ENABLED
    sso_proxy_header: str = "Remote-User"  # SECURITY_SSO_PROXY_HEADER
    sso_proxy_trusted_ips: str = "127.0.0.1,::1"  # SECURITY_SSO_PROXY_TRUSTED_IPS


class AgentGatewaySettings(BaseSettings):
    """Concurrent agent execution limits and timeouts."""

    model_config = SettingsConfigDict(env_prefix="AGENT_")

    max_concurrent: int = 20  # AGENT_MAX_CONCURRENT
    max_per_user: int = 3  # AGENT_MAX_PER_USER
    queue_timeout: float = 10.0  # AGENT_QUEUE_TIMEOUT (seconds)
    execution_timeout: float = 300.0  # AGENT_EXECUTION_TIMEOUT (seconds, idle silence threshold)
    execution_hard_ceiling: float = 3600.0  # AGENT_EXECUTION_HARD_CEILING (seconds, total wall-clock cap)
