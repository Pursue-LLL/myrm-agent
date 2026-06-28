"""配置 API 数据模型

[INPUT] pydantic::BaseModel (POS: 数据验证基础类)
[OUTPUT] ConfigSetRequest: 配置保存请求模型
[OUTPUT] ConfigRecord: 配置记录响应模型
[OUTPUT] OMNI_CONFIG_MODELS: Omni-Config 域配置模型映射字典
[POS] 配置服务 API 数据模型层。定义请求、响应结构以及 Omni-Config 强类型校验 Schema。
"""

from typing import Literal

from pydantic import BaseModel, Field

ConfigKey = Literal[
    "providers",
    "defaultModelConfig",
    "customModelInfo",
    "chatSettings",
    "personalSettings",
    "mcpServers",
    "searchServices",
    "commands",
    "retrieval",
    "channels",
    "voice",
    "securityConfig",
    "feishuCredentials",
    "dingtalkCredentials",
    "slackCredentials",
    "qqCredentials",
    "discordCredentials",
    "wecomCredentials",
    "wecomAibotCredentials",
    "wechatCredentials",
    "teamsCredentials",
    "matrixCredentials",
    "telegramCredentials",
    "googlechatCredentials",
    "whatsappCredentials",
    "smsCredentials",
    "externalAgents",
    "channelInstances",
    "channelLabels",
    "onboarding",
    "budget_policy",
    "companion_config",
    "backupSync",
    "proxySettings",
    "securityDashboardSettings",
    "browserCloudProvider",
    "browserProxy",
]

# ============================================================================
# Omni-Config: Domain-Specific Settings Models (Pre-flight Validation & Schema-Driven UI)
# ============================================================================

SearchServiceType = Literal[
    "perplexity",
    "tavily",
    "exa_ai",
    "parallel_ai",
    "google_pse",
    "dataforseo",
    "firecrawl",
    "searxng",
]


class SearchServiceConfigItem(BaseModel):
    """单条搜索服务配置"""

    id: str = Field(..., description="唯一标识符")
    name: str | None = Field(None, description="配置名称")
    enabled: bool = Field(default=False, description="是否启用")
    role: Literal["primary", "fallback"] = Field(..., description="主服务或备用服务")
    search_service: SearchServiceType = Field(..., description="搜索服务提供商类型")
    api_key: str | None = Field(None, description="API 密钥", json_schema_extra={"ui:widget": "password"})
    api_base: str | None = Field(None, description="自定义 API 基础地址")
    extra_params: dict[str, object] | None = Field(None, description="额外参数")
    latency: int | None = Field(None, description="延迟 (ms)")
    createdAt: int = Field(..., description="创建时间戳")


class SearchServicesConfigValue(BaseModel):
    """搜索服务配置集合"""

    searchServiceConfigs: list[SearchServiceConfigItem] = Field(default_factory=list, description="搜索服务配置列表")


def _personal_settings_field(
    section: str,
    *args: object,
    group: str = "basic",
    visible_if: str | None = None,
    requires_field: str | None = None,
    **kwargs: object,
) -> Field:
    """Attach x-ui-section / x-ui-group metadata for Schema-Driven UI filtering."""
    json_schema_extra = dict(kwargs.pop("json_schema_extra", {}) or {})
    json_schema_extra["x-ui-section"] = section
    if section == "preferences":
        json_schema_extra["x-ui-group"] = group
    if visible_if is not None:
        json_schema_extra["x-ui-visible-if"] = visible_if
    if requires_field is not None:
        json_schema_extra["x-ui-requires-field"] = requires_field
    return Field(*args, json_schema_extra=json_schema_extra, **kwargs)


class PersonalSettingsConfigValue(BaseModel):
    """个人偏好设置"""

    systemInstructions: str = _personal_settings_field("personalization", default="", description="系统指令")
    fetchRawWebpage: bool = _personal_settings_field("preferences", default=False, description="获取原始网页", group="advanced")
    extractDocumentText: bool = _personal_settings_field(
        "preferences",
        default=True,
        description="Extract text from PDF/Office attachments before sending to the model",
        group="advanced",
    )
    generateSearchSuggestions: bool = _personal_settings_field("preferences", default=True, description="生成搜索建议")
    enableCostEstimation: bool = _personal_settings_field(
        "preferences", default=True, description="启用成本估算", visible_if="local"
    )
    enableCacheBreakNotification: bool = _personal_settings_field(
        "preferences",
        default=False,
        description="启用缓存中断通知",
        group="advanced",
        visible_if="local",
        requires_field="enableCostEstimation",
    )
    showContextUsage: bool = _personal_settings_field(
        "preferences", default=True, description="显示上下文使用率", visible_if="local"
    )
    enableMemory: bool = _personal_settings_field("memory", default=False, description="启用记忆")
    memoryRequireConfirmation: bool = _personal_settings_field("memory", default=False, description="记忆需要确认")
    enableMemoryAutoExtraction: bool = _personal_settings_field("memory", default=True, description="启用记忆自动提取")
    enableAutoTitleGeneration: bool = _personal_settings_field("preferences", default=True, description="启用自动生成标题")
    webTtsProvider: Literal["browser", "openai", "elevenlabs", "fish_audio", "minimax", "edge"] = _personal_settings_field(
        "voice", default="browser", description="Web TTS 提供商"
    )
    timezone: str = _personal_settings_field("personalization", default="", description="时区")
    locale: str | None = _personal_settings_field("personalization", default=None, description="语言")
    customPrimaryColor: str | None = _personal_settings_field("personalization", default=None, description="自定义主色调")
    enableWebNotifications: bool = _personal_settings_field("notifications", default=True, description="启用 Web 通知")
    enableCompletionSound: bool = _personal_settings_field("notifications", default=True, description="启用完成提示音")
    notificationDeliveries: list[dict[str, object]] | None = _personal_settings_field(
        "notifications", default=None, description="通知投递配置"
    )
    privacyEnabled: bool | None = _personal_settings_field("security", default=None, description="启用隐私保护")
    privacyS2Action: str | None = _personal_settings_field("security", default=None, description="隐私 S2 动作")
    privacyS3Action: str | None = _personal_settings_field("security", default=None, description="隐私 S3 动作")
    codeExecutionAllowNetwork: bool = _personal_settings_field(
        "preferences",
        default=True,
        description="代码执行允许网络访问",
        group="advanced",
        visible_if="local",
    )
    enableEvalLab: bool = _personal_settings_field(
        "preferences",
        default=False,
        description="启用评测实验室",
        group="advanced",
        visible_if="local",
    )
    smoothStreamEnabled: bool = _personal_settings_field(
        "preferences", default=True, description="启用平滑流输出", group="advanced"
    )
    enterpriseTlsCompat: bool = _personal_settings_field(
        "preferences",
        default=False,
        description="Enterprise network compatibility (relaxes strict TLS for corporate proxies)",
        group="advanced",
    )
    publicIngressBaseUrl: str = _personal_settings_field("system", default="", description="公网 Ingress 地址")


class ProxyAuthMode(BaseModel):
    """Proxy authentication mode."""

    allow_any_key: bool = Field(
        default=False,
        description="When True, any non-empty Bearer token is accepted (Hermes-style open proxy). "
        "When False, only database-registered API keys are accepted.",
    )


class ProxySettingsConfigValue(BaseModel):
    """LLM passthrough proxy settings."""

    enabled: bool = Field(default=False, description="Enable the LLM passthrough proxy")
    auth: ProxyAuthMode = Field(default_factory=ProxyAuthMode, description="Authentication mode")


class SecurityDashboardSettingsConfigValue(BaseModel):
    """GitHub repos monitored on the Security Center dashboard (Dependabot PR supplement)."""

    monitoredGithubRepos: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Up to 3 GitHub owner/repo slugs (e.g. org/app)",
    )


BrowserCloudProviderType = Literal["browserbase", "browserless", "notte", "custom"]

_PROVIDER_WS_TEMPLATES: dict[str, str] = {
    "browserbase": "wss://connect.browserbase.com?apiKey={credential}",
    "browserless": "wss://production-sfo.browserless.io?token={credential}",
    "notte": "wss://us-prod.notte.cc/sessions/connect?token={credential}",
}


class BrowserCloudProviderConfigValue(BaseModel):
    """Cloud browser provider configuration for remote browsing via Browserbase/Browserless/Notte."""

    enabled: bool = Field(default=False, description="Whether cloud browser is enabled")
    provider: BrowserCloudProviderType = Field(default="browserbase", description="Cloud browser provider")
    credential: str = Field(default="", description="API key or token for the provider")
    custom_ws_url: str = Field(default="", description="Custom WebSocket CDP URL (only used when provider='custom')")

    def resolve_ws_endpoint(self) -> str | None:
        """Resolve the WebSocket endpoint URL from provider type and credential."""
        if not self.enabled or not self.credential:
            return None
        if self.provider == "custom":
            return self.custom_ws_url or None
        template = _PROVIDER_WS_TEMPLATES.get(self.provider)
        if template:
            return template.format(credential=self.credential)
        return None


class BrowserProxyConfigValue(BaseModel):
    """Browser proxy configuration for anti-detection browsing via residential/rotating proxies."""

    enabled: bool = Field(default=False, description="Whether browser proxy is enabled")
    proxies: list[str] = Field(
        default_factory=list,
        description="Proxy URL list (e.g. http://user:pass@host:port)",
    )


OMNI_CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "searchServices": SearchServicesConfigValue,
    "personalSettings": PersonalSettingsConfigValue,
    "proxySettings": ProxySettingsConfigValue,
    "securityDashboardSettings": SecurityDashboardSettingsConfigValue,
    "browserCloudProvider": BrowserCloudProviderConfigValue,
    "browserProxy": BrowserProxyConfigValue,
}

# ============================================================================
# Generic Config Models
# ============================================================================


class ConfigMeta(BaseModel):
    """配置元数据"""

    version: str = Field(..., description="版本号（时间戳_计数器格式）")
    updated_at: str = Field(..., alias="updatedAt", description="最后修改时间 (ISO 8601)")
    device_id: str = Field(..., alias="deviceId", description="最后修改的设备 ID")

    class Config:
        populate_by_name = True


class ConfigRecord(BaseModel):
    """配置记录"""

    key: ConfigKey
    value: dict[str, object]
    version: str
    updated_at: str = Field(..., alias="updatedAt")
    device_id: str = Field(..., alias="deviceId")
    encrypted: bool = False
    is_system_default: bool = Field(default=False, alias="isSystemDefault")

    class Config:
        populate_by_name = True


class ConfigSetRequest(BaseModel):
    """设置配置请求"""

    value: dict[str, object] = Field(..., description="配置值")
    expected_version: str | None = Field(None, alias="expectedVersion", description="期望的服务端版本（乐观锁）")
    device_id: str = Field(..., alias="deviceId", description="设备 ID")

    class Config:
        populate_by_name = True


class ConfigChange(BaseModel):
    """配置变更"""

    key: ConfigKey
    value: dict[str, object]
    expected_version: str | None = Field(
        None,
        alias="expectedVersion",
        description="期望的服务端版本（乐观锁），None 表示新配置",
    )
    timestamp: int

    class Config:
        populate_by_name = True


class ConfigSyncRequest(BaseModel):
    """批量同步请求"""

    changes: list[ConfigChange]
    device_id: str = Field(..., alias="deviceId")

    class Config:
        populate_by_name = True


class ConfigSyncResponse(BaseModel):
    """批量同步响应"""

    success: bool
    conflicts: list[ConfigKey] = Field(default_factory=list)
    new_versions: dict[str, str] = Field(default_factory=dict, alias="newVersions")
    error: str | None = None

    class Config:
        populate_by_name = True


class AllConfigsResponse(BaseModel):
    """获取所有配置响应"""

    configs: dict[str, ConfigRecord]


class ConflictErrorResponse(BaseModel):
    """版本冲突错误响应"""

    detail: str = "Version conflict"
    server_version: str = Field(..., alias="serverVersion")

    class Config:
        populate_by_name = True
