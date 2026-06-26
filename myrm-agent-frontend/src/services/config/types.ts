/**
 * 配置同步系统类型定义
 *
 * 统一的配置数据结构，支持：
 * - 版本控制（乐观锁）
 * - 字段级变更追踪
 * - 多设备同步
 */

import type { ProviderConfig, DefaultModelConfig, CustomModelInfo } from '@/store/config/providerTypes';
import type { MCPServiceConfig, SearchServiceConfigItem } from '@/store/config/types';
import type {
  ChannelsConfig,
  DiscordCredentials,
  DingTalkCredentials,
  FeishuCredentials,
  GoogleChatCredentials,
  MatrixCredentials,
  SlackCredentials,
  TeamsCredentials,
  TelegramCredentials,
  WeComCredentials,
  WeChatCredentials,
} from '@/services/channels';

// ============================================================================
// 配置键定义
// ============================================================================

/**
 * 配置键类型
 *
 * 每个键对应一类配置数据：
 * - providers: 模型服务商配置（敏感）
 * - chatSettings: 聊天设置
 * - personalSettings: 个人偏好设置
 * - mcpServers: MCP 服务器配置（敏感）
 * - searchServices: 搜索服务配置（敏感）
 * - commands: 用户自定义命令
 * - retrieval: 检索配置（敏感）
 * - channels: 通知渠道配置
 * - voice: 语音配置
 * - securityConfig: 安全策略配置
 * - *Credentials: 各平台凭证配置（敏感）
 */
export type ConfigKey =
  | 'providers'
  | 'defaultModelConfig'
  | 'customModelInfo'
  | 'chatSettings'
  | 'personalSettings'
  | 'mcpServers'
  | 'searchServices'
  | 'commands'
  | 'retrieval'
  | 'channels'
  | 'voice'
  | 'securityConfig'
  | 'externalAgents'
  | 'feishuCredentials'
  | 'dingtalkCredentials'
  | 'slackCredentials'
  | 'discordCredentials'
  | 'wecomCredentials'
  | 'wechatCredentials'
  | 'teamsCredentials'
  | 'matrixCredentials'
  | 'telegramCredentials'
  | 'googlechatCredentials'
  | 'budget_policy'
  | 'backupSync'
  | 'proxySettings'
  | 'securityDashboardSettings'
  | 'browserCloudProvider';

/** 所有配置键（用于按需加载） */
export const ALL_CONFIG_KEYS: readonly ConfigKey[] = [
  'providers',
  'defaultModelConfig',
  'customModelInfo',
  'chatSettings',
  'personalSettings',
  'mcpServers',
  'searchServices',
  'commands',
  'retrieval',
  'channels',
  'voice',
  'securityConfig',
  'externalAgents',
  'feishuCredentials',
  'dingtalkCredentials',
  'slackCredentials',
  'discordCredentials',
  'wecomCredentials',
  'wechatCredentials',
  'teamsCredentials',
  'matrixCredentials',
  'telegramCredentials',
  'googlechatCredentials',
  'budget_policy',
  'backupSync',
  'proxySettings',
  'securityDashboardSettings',
  'browserCloudProvider',
] as const;

/** 首屏核心配置（优先加载以加快启动） */
export const CORE_CONFIG_KEYS: readonly ConfigKey[] = [
  'providers',
  'defaultModelConfig',
  'customModelInfo',
  'chatSettings',
  'personalSettings',
] as const;

// ============================================================================
// 配置值类型映射
// ============================================================================

/**
 * Providers 配置值
 */
export interface ProvidersConfigValue {
  providers: ProviderConfig[];
  defaultModelConfig: DefaultModelConfig;
  customModelInfo: Record<string, CustomModelInfo>;
}

/**
 * ChatSettings 配置值
 */
export interface ChatSettingsConfigValue {
  defaultModelConfig: DefaultModelConfig;
  customModelInfo: Record<string, CustomModelInfo>;
}

/**
 * PersonalSettings 配置值
 */
export type WebTtsProvider = 'browser' | 'openai' | 'elevenlabs' | 'fish_audio' | 'minimax' | 'edge';

export interface NotificationDelivery {
  channel: string;
  target: string;
}

export type PIIAction = 'warn' | 'redact' | 'pseudonymize' | 'block';

export type PrivacyS2Strategy = 'cloud_after_redact' | 'local';
export type PrivacyS3Strategy = 'local' | 'block';
export type PrivacyLocalFallback = 'block' | 'force_redact_cloud';

export interface PrivacyRoutingConfig {
  localModel?: string;
  localBaseUrl?: string;
  localApiKey?: string;
  s2Strategy?: PrivacyS2Strategy;
  s3Strategy?: PrivacyS3Strategy;
  localFallback?: PrivacyLocalFallback;
}

export type ImageGenerationProvider = 'openai' | 'gemini' | 'stability';
export type VideoGenerationProvider = 'openai' | 'gemini' | 'qwen' | 'minimax';

export interface ImageGenerationConfig {
  model: string;
  fallbackModels: string[];
  defaultSize: string;
  defaultQuality: string;
  timeoutSeconds: number;
  maxRetries: number;
}

export interface VideoGenerationConfig {
  provider: VideoGenerationProvider;
  model: string;
  fallbackProviders: Array<{ provider: string; model: string }>;
  timeoutSeconds: number;
  maxRetries: number;
  defaultAspectRatio?: string;
  defaultResolution?: string;
  defaultDurationSeconds?: number;
}

export interface PersonalSettingsConfigValue {
  systemInstructions: string;
  fetchRawWebpage: boolean;
  extractDocumentText: boolean;
  generateSearchSuggestions: boolean;
  enableCostEstimation: boolean;
  enableCacheBreakNotification: boolean;
  showContextUsage: boolean;
  enableMemory: boolean;
  memoryRequireConfirmation: boolean;
  enableMemoryAutoExtraction: boolean;
  preCompactEnabled: boolean;
  preCompactBudgetTokens: number;
  enableAutoTitleGeneration: boolean;
  webTtsProvider: WebTtsProvider;
  timezone: string;
  locale?: string;
  customPrimaryColor?: string;
  enableWebNotifications: boolean;
  enableCompletionSound: boolean;
  enableIdleApprovalNotification: boolean;
  approvalNotificationSound: boolean;
  notificationDeliveries?: NotificationDelivery[];
  privacyEnabled?: boolean;
  privacyS2Action?: PIIAction;
  privacyS3Action?: PIIAction;
  privacyDeepScan?: boolean;
  privacyRouting?: PrivacyRoutingConfig;
  privacyCustomKeywordsS2?: string[];
  privacyCustomKeywordsS3?: string[];
  privacyCustomPatternsS2?: string[];
  privacyCustomPatternsS3?: string[];
  privacySensitiveToolsS2?: string[];
  privacySensitiveToolsS3?: string[];
  imageGeneration?: ImageGenerationConfig;
  videoGeneration?: VideoGenerationConfig;
  codeExecutionAllowNetwork?: boolean;
  enableEvalLab?: boolean;
  smoothStreamEnabled?: boolean;
  publicIngressBaseUrl?: string;
  enterpriseTlsCompat?: boolean;
}

/**
 * MCPServers 配置值
 */
export interface MCPServersConfigValue {
  mcpConfigs: MCPServiceConfig[];
}

/**
 * SearchServices 配置值
 */
export interface SearchServicesConfigValue {
  searchServiceConfigs: SearchServiceConfigItem[];
}

/**
 * Commands 配置值（用户自定义命令）
 */
export interface CommandsConfigValue {
  commands: SlashCommand[];
  recentCommandIds: string[];
}

// 导入命令类型
import type { SlashCommand } from '@/types/command';

/**
 * Retrieval Provider/Model 配置
 */
export interface RetrievalProviderModelConfig {
  provider: string;
  model: string;
  apiKey: string;
  apiBase?: string;
}

/**
 * Retrieval 配置值（Embedding/Reranker，敏感）
 */
export interface RetrievalConfigValue {
  embeddingConfig?: RetrievalProviderModelConfig;
  embeddingApplied?: boolean;
  embeddingAppliedAt?: number;
  rerankerConfig?: RetrievalProviderModelConfig;
  rerankerApplied?: boolean;
  rerankerAppliedAt?: number;
  enableAdvancedRetrieval?: boolean;
}

/**
 * 通知渠道配置值
 */
export type ChannelsConfigValue = ChannelsConfig;

/**
 * 语音配置值
 */
export interface VoiceConfigValue {
  sttEnabled: boolean;
  sttProvider: string;
  sttApiKey: string;
  sttModel: string;
  sttLanguage: string;
  sttLocalModel: string;
  sttLocalDevice: string;
  sttLocalComputeType: string;
  sttBaseUrl: string;
  ttsMode: string;
  ttsProvider: string;
  ttsApiKey: string;
  ttsBaseUrl: string;
  ttsVoice: string;
  ttsMaxLength: number;
  ttsSummaryEnabled: boolean;
  ttsSummaryThreshold: number;
  ttsSummaryModel: string;
}

/**
 * Feishu 凭证配置值
 */
export type FeishuCredentialsConfigValue = FeishuCredentials;

/**
 * External Agent runtime type.
 */
export type ExternalAgentType = 'cli' | 'acp' | 'sdk';

/**
 * External Agent permission mode.
 */
export type ExternalAgentPermissionMode = 'allow_all' | 'ask' | 'safe';

/**
 * External Agent authentication mode.
 *
 * - `subscription`: delegate runs on the user's own model plan via the CLI's
 *   own login state; the host strips provider API keys from the child env.
 * - `api_key`: the host injects provider API keys from the agent's `env`.
 */
export type ExternalAgentAuthMode = 'subscription' | 'api_key';

/**
 * Single external agent configuration.
 */
export interface ExternalAgentConfig {
  name: string;
  type: ExternalAgentType;
  command: string;
  args?: string[];
  enabled: boolean;
  permissionMode: ExternalAgentPermissionMode;
  authMode?: ExternalAgentAuthMode;
  description?: string;
  maxTurns?: number;
}

/**
 * ExternalAgents configuration value stored via ConfigSyncManager.
 */
export interface ExternalAgentsConfigValue {
  agents: ExternalAgentConfig[];
}

/**
 * Permission Engine — tool execution access control.
 */
export type PermissionAction = 'allow' | 'ask' | 'deny';

export interface PermissionRuleConfig {
  permission: string;
  pattern: string;
  action: PermissionAction;
}

export interface PathPolicyConfig {
  allowedRoots?: string[];
}

export interface SecurityConfigValue {
  permissions: Record<string, PermissionAction | Record<string, PermissionAction>>;
  approvalTimeoutSeconds: number;
  approvalTimeoutBehavior?: 'deny' | 'allow';
  pathPolicy?: PathPolicyConfig;
  networkAllowlist?: string[];
  domainHitlEnabled?: boolean;
  yoloModeEnabled?: boolean;
  yoloModeEnabledAt?: number;
  yoloModeTimeout?: number;
  autoReviewEnabled?: boolean;
  autoReviewModel?: string;
}

export interface BudgetPolicyConfigValue {
  enabled: boolean;
  daily_limit_usd: number | null;
  session_limit_usd: number | null;
  per_call_limit_usd: number | null;
  warning_threshold: number;
  finalization_reserve_pct: number;
  action_on_exceeded: 'warn' | 'block' | 'finalize';
}

export interface BackupSyncConfigValue {
  enabled: boolean;
  provider: 'webdav' | 's3';
  autoSync: boolean;
  syncInterval: number;
  maxBackups: number;
  deviceName: string;
  webdav: {
    host: string;
    username: string;
    password: string;
    path: string;
  };
  s3: {
    endpoint: string;
    region: string;
    bucket: string;
    accessKeyId: string;
    secretAccessKey: string;
    prefix: string;
    forcePathStyle: boolean;
  };
}

/**
 * LLM proxy passthrough settings.
 */
export interface ProxyAuthMode {
  allow_any_key: boolean;
}

export interface ProxySettingsConfigValue {
  enabled: boolean;
  auth: ProxyAuthMode;
}

export interface SecurityDashboardSettingsConfigValue {
  monitoredGithubRepos: string[];
}

export type BrowserCloudProviderType = 'browserbase' | 'browserless' | 'notte' | 'custom';

export interface BrowserCloudProviderConfigValue {
  enabled: boolean;
  provider: BrowserCloudProviderType;
  credential: string;
  custom_ws_url: string;
}

/**
 * 配置键到值类型的映射
 */
export interface ConfigValueMap {
  providers: ProvidersConfigValue;
  defaultModelConfig: DefaultModelConfig;
  customModelInfo: Record<string, CustomModelInfo>;
  chatSettings: ChatSettingsConfigValue;
  personalSettings: PersonalSettingsConfigValue;
  mcpServers: MCPServersConfigValue;
  searchServices: SearchServicesConfigValue;
  commands: CommandsConfigValue;
  retrieval: RetrievalConfigValue;
  channels: ChannelsConfigValue;
  voice: VoiceConfigValue;
  feishuCredentials: FeishuCredentialsConfigValue;
  dingtalkCredentials: DingTalkCredentials;
  slackCredentials: SlackCredentials;
  discordCredentials: DiscordCredentials;
  wecomCredentials: WeComCredentials;
  wechatCredentials: WeChatCredentials;
  teamsCredentials: TeamsCredentials;
  matrixCredentials: MatrixCredentials;
  telegramCredentials: TelegramCredentials;
  googlechatCredentials: GoogleChatCredentials;
  securityConfig: SecurityConfigValue;
  externalAgents: ExternalAgentsConfigValue;
  budget_policy: BudgetPolicyConfigValue;
  backupSync: BackupSyncConfigValue;
  proxySettings: ProxySettingsConfigValue;
  securityDashboardSettings: SecurityDashboardSettingsConfigValue;
  browserCloudProvider: BrowserCloudProviderConfigValue;
}

/**
 * 敏感配置键
 *
 * 这些键包含 API Key、密钥或其他敏感数据。
 */
export const SENSITIVE_CONFIG_KEYS: readonly ConfigKey[] = [
  'providers',
  'retrieval',
  'mcpServers',
  'searchServices',
  'feishuCredentials',
  'dingtalkCredentials',
  'slackCredentials',
  'discordCredentials',
  'wecomCredentials',
  'wechatCredentials',
  'teamsCredentials',
  'matrixCredentials',
  'telegramCredentials',
  'googlechatCredentials',
  'backupSync',
  'browserCloudProvider',
];

/**
 * 判断配置是否敏感
 */
export function isSensitiveConfig(key: string): boolean {
  return SENSITIVE_CONFIG_KEYS.includes(key as ConfigKey);
}

// ============================================================================
// 配置元数据
// ============================================================================

/**
 * 配置版本号
 *
 * 格式：timestamp_counter
 * - timestamp: Unix 毫秒时间戳
 * - counter: 同一毫秒内的递增计数器
 *
 * 示例：1706000000000_0, 1706000000000_1
 */
export type ConfigVersion = string;

/**
 * 配置元数据
 */
export interface ConfigMeta {
  /** 版本号（时间戳_计数器格式） */
  version: ConfigVersion;
  /** 最后修改时间 (ISO 8601) */
  updatedAt: string;
  /** 最后修改的设备 ID */
  deviceId: string;
}

/**
 * 完整配置记录
 */
export interface ConfigRecord<K extends ConfigKey = ConfigKey> {
  key: K;
  value: ConfigValueMap[K];
  meta: ConfigMeta;
  /** 是否服务端加密存储（只读标志，由后端自动管理） */
  encrypted?: boolean;
  /** 该配置来自 __system__ 默认配置，用户尚未自定义 */
  isSystemDefault?: boolean;
}

// ============================================================================
// 版本号工具函数
// ============================================================================

/**
 * 创建初始版本号
 */
export function createInitialVersion(): ConfigVersion {
  return `${Date.now()}_0`;
}

/**
 * 递增版本号
 */
export function incrementVersion(current: ConfigVersion): ConfigVersion {
  const now = Date.now();
  const [timestamp, counter] = current.split('_').map(Number);

  if (timestamp === now) {
    return `${now}_${counter + 1}`;
  }
  return `${now}_0`;
}

/**
 * 比较版本号
 *
 * @returns 正数表示 a > b，负数表示 a < b，0 表示相等
 */
export function compareVersions(a: ConfigVersion, b: ConfigVersion): number {
  const [aTs, aCtr] = a.split('_').map(Number);
  const [bTs, bCtr] = b.split('_').map(Number);

  if (aTs !== bTs) return aTs - bTs;
  return aCtr - bCtr;
}

/**
 * 解析版本号
 */
export function parseVersion(version: ConfigVersion): { timestamp: number; counter: number } {
  const [timestamp, counter] = version.split('_').map(Number);
  return { timestamp, counter };
}

// ============================================================================
// 同步相关类型
// ============================================================================

/**
 * 字段变更记录
 */
export interface FieldChange {
  /** 字段路径，如 ['providers', 0, 'apiKey'] */
  path: (string | number)[];
  /** 变更前的值 */
  oldValue: unknown;
  /** 变更后的值 */
  newValue: unknown;
}

/**
 * 配置变更记录
 */
export interface ConfigChange<K extends ConfigKey = ConfigKey> {
  key: K;
  /** 完整的新值 */
  value: ConfigValueMap[K];
  /** 期望的服务端版本（乐观锁） */
  expectedVersion: ConfigVersion;
  /** 变更时间戳 */
  timestamp: number;
}

/**
 * 同步结果
 */
export interface SyncResult {
  /** 是否成功 */
  success: boolean;
  /** 版本冲突的配置键 */
  conflicts: ConfigKey[];
  /** 更新后的版本号 */
  newVersions: Map<ConfigKey, ConfigVersion>;
  /** 错误信息（如果有） */
  error?: string;
}

// ============================================================================
// 适配器接口
// ============================================================================

/**
 * 配置适配器接口
 *
 * 所有部署模式（Tauri/Sandbox）都实现此接口
 */
export interface ConfigAdapter {
  /**
   * 获取配置
   * @param keys 可选，只加载指定键，减少传输量（Sandbox 模式优化）
   */
  getAll(keys?: readonly ConfigKey[]): Promise<Map<ConfigKey, ConfigRecord>>;

  /**
   * 获取单个配置
   */
  get<K extends ConfigKey>(key: K): Promise<ConfigRecord<K> | null>;

  /**
   * 设置配置（带版本号）
   *
   * @throws ConfigConflictError 版本冲突时抛出
   */
  set<K extends ConfigKey>(key: K, value: ConfigValueMap[K], expectedVersion?: ConfigVersion): Promise<ConfigRecord<K>>;

  /**
   * 删除配置
   */
  delete(key: ConfigKey): Promise<boolean>;

  /**
   * 批量同步
   */
  sync(changes: ConfigChange[]): Promise<SyncResult>;
}

// ============================================================================
// 错误类型
// ============================================================================

/**
 * 配置版本冲突错误
 */
export class ConfigConflictError extends Error {
  constructor(
    public readonly key: ConfigKey,
    public readonly localVersion: ConfigVersion,
    public readonly serverVersion: ConfigVersion,
  ) {
    super(`Config conflict for key '${key}': local=${localVersion}, server=${serverVersion}`);
    this.name = 'ConfigConflictError';
  }
}

/**
 * 配置同步错误
 */
export class ConfigSyncError extends Error {
  constructor(
    message: string,
    public readonly cause?: Error,
  ) {
    super(message);
    this.name = 'ConfigSyncError';
  }
}

// ============================================================================
// 默认值
// ============================================================================

/**
 * 默认的 PersonalSettings 配置
 */
export const DEFAULT_PERSONAL_SETTINGS: PersonalSettingsConfigValue = {
  systemInstructions: '',
  fetchRawWebpage: false,
  extractDocumentText: true,
  generateSearchSuggestions: true,
  enableCostEstimation: true,
  enableCacheBreakNotification: false,
  showContextUsage: true,
  enableMemory: false,
  memoryRequireConfirmation: false,
  enableMemoryAutoExtraction: true,
  preCompactEnabled: true,
  preCompactBudgetTokens: 1500,
  enableAutoTitleGeneration: true,
  webTtsProvider: 'browser',
  timezone: '',
  enableWebNotifications: true,
  enableCompletionSound: true,
  enableIdleApprovalNotification: true,
  approvalNotificationSound: true,
  codeExecutionAllowNetwork: true,
  enableEvalLab: false,
  smoothStreamEnabled: true,
  publicIngressBaseUrl: '',
};

/**
 * 默认的 MCPServers 配置
 */
export const DEFAULT_MCP_SERVERS: MCPServersConfigValue = {
  mcpConfigs: [],
};

/**
 * 默认的 SearchServices 配置
 */
export const DEFAULT_SEARCH_SERVICES: SearchServicesConfigValue = {
  searchServiceConfigs: [],
};

/**
 * 默认的 Commands 配置
 */
export const DEFAULT_COMMANDS: CommandsConfigValue = {
  commands: [],
  recentCommandIds: [],
};

/**
 * 默认的 Retrieval 配置
 */
export const DEFAULT_RETRIEVAL: RetrievalConfigValue = {
  embeddingConfig: {
    provider: 'siliconflow',
    model: 'BAAI/bge-m3',
    apiKey: '',
    apiBase: '',
  },
  embeddingApplied: false,
  embeddingAppliedAt: undefined,
  rerankerConfig: {
    provider: 'siliconflow',
    model: 'BAAI/bge-reranker-v2-m3',
    apiKey: '',
    apiBase: '',
  },
  rerankerApplied: false,
  rerankerAppliedAt: undefined,
};
