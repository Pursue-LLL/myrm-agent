/**
 * 配置同步服务
 *
 * 统一的配置存储与同步方案，支持：
 * - Tauri 模式（Desktop + WebUI）：本地全量加载
 * - Sandbox 模式（云端 + 服务端加密）：核心配置优先加载，其余后台预加载
 *
 * 核心特性：
 * - 单一数据源：数据库是唯一权威数据源
 * - 乐观更新：先更新 UI，再异步同步
 * - 差量同步：只同步变更的配置
 * - 版本控制：乐观锁冲突检测
 * - 离线支持：网络不可用时保存到本地队列
 * - 按需加载：getAll(keys?) 支持指定键减少传输量
 */

// 类型导出
export type {
  ConfigKey,
  ConfigVersion,
  ConfigRecord,
  ConfigMeta,
  ConfigChange,
  ConfigAdapter,
  SyncResult,
  ConfigValueMap,
  ProvidersConfigValue,
  ChatSettingsConfigValue,
  PersonalSettingsConfigValue,
  MCPServersConfigValue,
  SearchServicesConfigValue,
  CommandsConfigValue,
  RetrievalConfigValue,
  RetrievalProviderModelConfig,
  ExternalAgentConfig,
  ExternalAgentType,
  ExternalAgentPermissionMode,
  ExternalAgentAuthMode,
  ExternalAgentsConfigValue,
  BackupSyncConfigValue,
  ProxySettingsConfigValue,
  ProxyAuthMode,
  BrowserCloudProviderConfigValue,
  BrowserCloudProviderType,
  BrowserProxyConfigValue,
  CaptchaSolverConfigValue,
  WebFetchEscalationConfigValue,
} from './types';

// 工具函数导出
export {
  createInitialVersion,
  incrementVersion,
  compareVersions,
  parseVersion,
  DEFAULT_PERSONAL_SETTINGS,
  DEFAULT_MCP_SERVERS,
  DEFAULT_SEARCH_SERVICES,
  DEFAULT_COMMANDS,
  DEFAULT_RETRIEVAL,
} from './types';

// 错误类型导出
export { ConfigConflictError, ConfigSyncError } from './types';

// 适配器导出
export { BaseConfigAdapter, TauriConfigAdapter, SandboxConfigAdapter } from './adapters';

// 同步管理器导出
export {
  ConfigSyncManager,
  getConfigSyncManager,
  resetConfigSyncManager,
  type SyncStatus,
  type ConfigChangeListener,
} from './ConfigSyncManager';
