// 搜索服务类型（LiteLLM 统一架构）
export type SearchServiceType =
  | 'perplexity'
  | 'tavily'
  | 'exa_ai'
  | 'parallel_ai'
  | 'google_pse'
  | 'dataforseo'
  | 'firecrawl'
  | 'searxng';

// 搜索服务配置接口（基础配置，用于API请求）
export interface SearchServiceConfig {
  search_service: SearchServiceType;
  api_key?: string | null;
  api_base?: string | null;
  extra_params?: Record<string, unknown> | null;
  fallback_config?: SearchServiceConfig | null; // 备用搜索服务配置
}

// 搜索服务配置项（带元数据，用于多配置管理）
export interface SearchServiceConfigItem {
  id: string;
  name?: string | null;
  enabled: boolean;
  role: 'primary' | 'fallback'; // 主服务或备用服务（最多 1 主 + 1 备同时启用）
  search_service: SearchServiceType;
  api_key?: string | null;
  api_base?: string | null;
  extra_params?: Record<string, unknown> | null;
  latency?: number | null;
  createdAt: number; // 创建时间戳
}

// MCP OAuth 配置
export interface MCPOAuthSettings {
  authorizationEndpoint: string;
  tokenEndpoint: string;
  clientId: string;
  clientSecret?: string;
  scope?: string;
}

// MCP服务配置接口
export interface MCPServiceConfig {
  name: string;
  type: 'sse' | 'stdio' | 'streamable_http';
  url?: string | null;
  command?: string | null;
  args?: string[] | null;
  description: string;
  enabled: boolean;
  headers?: Record<string, string> | null;
  extra_params?: Record<string, unknown> | null;
  connectTimeout?: number | null;
  executeTimeout?: number | null;
  sslVerify?: boolean | string | null;
  clientCert?: string | null;
  clientKey?: string | null;
  clientKeyPassword?: string | null;
  oauth?: MCPOAuthSettings | null;
  lastScanSummary?: MCPLastScanSummary | null;
}

export interface MCPLastScanSummary {
  maxSeverity: string | null;
  scannedAt: number;
  findingCount: number;
}

export interface MCPScanFinding {
  threatType: string;
  severity: string;
  description: string;
  field: string;
  recommendation?: string;
}

export interface MCPScanResult {
  serverName: string;
  allowSave: boolean;
  requiresAcknowledgement: boolean;
  maxSeverity: string | null;
  findings: MCPScanFinding[];
}

export interface MCPScanBatchResult {
  results: MCPScanResult[];
}

// 验证结果类型定义
export interface ValidationResult {
  success: boolean;
  message?: string;
  latency?: number;
  instructions?: string;
  retriable?: boolean;
  businessCode?: string;
  scanFindings?: MCPScanFinding[];
}

// Store状态接口
export interface ConfigState {
  // 系统指令
  systemInstructions: string;

  // 高级配置
  fetchRawWebpage: boolean;
  extractDocumentText: boolean;
  generateSearchSuggestions: boolean;

  // 成本计算开关
  enableCostEstimation: boolean;

  // Cache break 实时通知开关（默认关闭）
  enableCacheBreakNotification: boolean;

  // 上下文窗口使用率展示开关
  showContextUsage: boolean;

  // 记忆功能开关
  enableMemory: boolean;
  // 记忆保存前是否需要用户确认
  memoryRequireConfirmation: boolean;
  // 是否使用轻量模型自动从会话中提取记忆
  enableMemoryAutoExtraction: boolean;
  // 是否启用历史会话搜索工具（conversation_search_tool）
  memoryEnableConversationSearch: boolean;
  preCompactEnabled: boolean;
  preCompactBudgetTokens: number;

  // AI 自动生成标题开关
  enableAutoTitleGeneration: boolean;

  // Web 端 TTS 朗读服务商
  webTtsProvider: import('@/services/config/types').WebTtsProvider;
  customPrimaryColor?: string;

  // 用户时区（IANA 格式，如 "Asia/Shanghai"），空字符串表示自动检测
  timezone: string;

  // Web 实时通知（SSE）开关
  enableWebNotifications: boolean;

  // 任务完成提示音
  enableCompletionSound: boolean;

  // 空闲审批通知（窗口不活跃时系统级通知）
  enableIdleApprovalNotification: boolean;
  approvalNotificationSound: boolean;

  // PII 隐私保护
  privacyEnabled: boolean;
  privacyS2Action: import('@/services/config/types').PIIAction;
  privacyS3Action: import('@/services/config/types').PIIAction;
  privacyDeepScan: boolean;
  privacyRouting: import('@/services/config/types').PrivacyRoutingConfig;
  privacyCustomKeywordsS2: string[];
  privacyCustomKeywordsS3: string[];
  privacyCustomPatternsS2: string[];
  privacyCustomPatternsS3: string[];
  privacySensitiveToolsS2: string[];
  privacySensitiveToolsS3: string[];

  // 代码执行网络权限
  codeExecutionAllowNetwork: boolean;

  // 评测实验室开关
  enableEvalLab: boolean;

  // 平滑流式渲染开关
  smoothStreamEnabled: boolean;

  // 工作流模式自动建议开关
  suggestWorkflowMode: boolean;

  // 公网访问地址 (Public Ingress Base URL)
  publicIngressBaseUrl?: string;

  // 媒体生成配置
  imageGeneration?: import('@/services/config/types').ImageGenerationConfig;
  videoGeneration?: import('@/services/config/types').VideoGenerationConfig;

  // 搜索服务配置列表（支持多配置，单启用）
  searchServiceConfigs: SearchServiceConfigItem[];

  // MCP服务配置
  mcpConfigs: MCPServiceConfig[];
  orgMcpConfigs: MCPServiceConfig[];

  // 设置方法
  setFetchRawWebpage: (fetch: boolean) => void;
  setExtractDocumentText: (enabled: boolean) => void;
  setGenerateSearchSuggestions: (generate: boolean) => void;
  setSystemInstructions: (instructions: string) => void;
  setEnableCostEstimation: (enable: boolean) => void;
  setEnableCacheBreakNotification: (enable: boolean) => void;
  setShowContextUsage: (show: boolean) => void;
  setEnableMemory: (enable: boolean) => void;
  setMemoryRequireConfirmation: (enable: boolean) => void;
  setEnableMemoryAutoExtraction: (enable: boolean) => void;
  setMemoryEnableConversationSearch: (enable: boolean) => void;
  setPreCompactEnabled: (enable: boolean) => void;
  setPreCompactBudgetTokens: (tokens: number) => void;
  setEnableAutoTitleGeneration: (enable: boolean) => void;
  setWebTtsProvider: (provider: import('@/services/config/types').WebTtsProvider) => void;
  setCustomPrimaryColor: (color: string | undefined) => void;
  updatePersonalSettings: (
    settings: Partial<import('@/services/config/types').PersonalSettingsConfigValue>,
  ) => Promise<void>;
  setTimezone: (tz: string) => void;
  setEnableWebNotifications: (enable: boolean) => void;
  setEnableCompletionSound: (enable: boolean) => void;
  setEnableIdleApprovalNotification: (enable: boolean) => void;
  setApprovalNotificationSound: (enable: boolean) => void;
  setPrivacyEnabled: (enable: boolean) => void;
  setPrivacyS2Action: (action: import('@/services/config/types').PIIAction) => void;
  setPrivacyS3Action: (action: import('@/services/config/types').PIIAction) => void;
  setPrivacyDeepScan: (enable: boolean) => void;
  setPrivacyRouting: (config: import('@/services/config/types').PrivacyRoutingConfig) => void;
  setPrivacyCustomKeywordsS2: (keywords: string[]) => void;
  setPrivacyCustomKeywordsS3: (keywords: string[]) => void;
  setPrivacyCustomPatternsS2: (patterns: string[]) => void;
  setPrivacyCustomPatternsS3: (patterns: string[]) => void;
  setPrivacySensitiveToolsS2: (tools: string[]) => void;
  setPrivacySensitiveToolsS3: (tools: string[]) => void;
  setCodeExecutionAllowNetwork: (allow: boolean) => void;
  setEnableEvalLab: (enable: boolean) => void;
  setSmoothStreamEnabled: (enable: boolean) => void;
  setPublicIngressBaseUrl: (url: string | undefined) => void;

  personalSettings?: import('@/services/config/types').PersonalSettingsConfigValue;
  _configStoreReady?: boolean;
  setNotificationDeliveries: (deliveries: import('@/services/config/types').NotificationDelivery[] | undefined) => void;
  setImageGeneration: (config: import('@/services/config/types').ImageGenerationConfig | undefined) => void;
  setVideoGeneration: (config: import('@/services/config/types').VideoGenerationConfig | undefined) => void;

  // MCP配置管理方法
  setMCPConfigs: (configs: MCPServiceConfig[]) => void;
  addMCPConfig: (config: MCPServiceConfig) => void;
  updateMCPConfig: (index: number, config: MCPServiceConfig) => void;
  removeMCPConfig: (index: number) => void;
  toggleMCPConfig: (index: number) => void;

  // 搜索服务配置管理方法
  setSearchServiceConfigs: (configs: SearchServiceConfigItem[]) => void;
  addSearchServiceConfig: (config: SearchServiceConfigItem) => void;
  updateSearchServiceConfig: (id: string, config: Partial<SearchServiceConfigItem>) => void;
  removeSearchServiceConfig: (id: string) => void;
  enableSearchServiceConfig: (id: string) => void;
  getActiveSearchServiceConfig: () => SearchServiceConfig | null;

  // 配置导出导入方法
  exportConfig: () => string;
  importConfig: (configJson: string) => Promise<{ success: boolean; messageKey: string }>;

  // 初始化配置（从后端加载）
  initConfig: () => Promise<void>;

  // 验证方法
  validateSearchServiceConfig: (config: SearchServiceConfig) => Promise<ValidationResult>;
  validateMCPConfig: (config: MCPServiceConfig) => Promise<ValidationResult>;
}
