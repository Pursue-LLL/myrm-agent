"""[INPUT]
- .constants (POS: BASE_DIR)

[OUTPUT]
- DingTalkChannelSettings, McpSettings, BrowserPoolSettings, WebUISettings

[POS]
Application settings: channel, MCP and browser-pool settings.
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class DingTalkChannelSettings(BaseSettings):
    """DingTalk channel API HTTP timeouts (seconds)."""

    model_config = SettingsConfigDict(env_prefix="CHANNEL_DINGTALK_")

    timeout: float = 15.0  # CHANNEL_DINGTALK_TIMEOUT
    media_timeout: float = 30.0  # CHANNEL_DINGTALK_MEDIA_TIMEOUT
    download_timeout: float = 60.0  # CHANNEL_DINGTALK_DOWNLOAD_TIMEOUT


class McpSettings(BaseSettings):
    """MCP transport and SSRF protection policy."""

    model_config = SettingsConfigDict(env_prefix="MCP_")

    allow_stdio: bool = True  # MCP_ALLOW_STDIO
    require_https: bool = True  # MCP_REQUIRE_HTTPS
    enable_ssrf_protection: bool = True  # MCP_ENABLE_SSRF_PROTECTION
    verify_timeout: int = 10  # MCP_VERIFY_TIMEOUT (seconds)
    max_response_size: int = 10 * 1024 * 1024  # MCP_MAX_RESPONSE_SIZE (bytes)


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
