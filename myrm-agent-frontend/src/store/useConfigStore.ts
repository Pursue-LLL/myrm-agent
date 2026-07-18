/**
 * 配置 Store
 *
 * 统一的配置状态管理，集成 ConfigSyncManager 实现：
 * - 乐观更新：先更新 UI，再异步同步
 * - 自动同步：配置变更自动同步到后端
 * - 离线支持：网络不可用时保存到本地队列
 */

import { create } from 'zustand';
import {
  getConfigSyncManager,
  type PersonalSettingsConfigValue,
  type MCPServersConfigValue,
  type SearchServicesConfigValue,
  DEFAULT_PERSONAL_SETTINGS,
  DEFAULT_MCP_SERVERS,
  DEFAULT_SEARCH_SERVICES,
} from '@/services/config';
import { normalizePersonalSettings } from '@/services/config/configNormalizer';
import { invalidateLocalCapabilitiesProbeCache } from '@/services/localCapabilitiesProbe';
import * as mcpManager from './config/mcp';
import * as searchServiceManager from './config/searchService';
import * as importExportManager from './config/importExport';
import * as validation from './config/validation';
import type { ConfigState, MCPServiceConfig, SearchServiceConfigItem, SearchServiceConfig } from './config/types';
import { normalizePublicIngressBaseUrl, isValidPublicIngressBaseUrl } from '@/lib/utils/urlUtils';

// 同步管理器
const syncManager = getConfigSyncManager();

/**
 * 同步 PersonalSettings 到后端
 */
const syncPersonalSettings = (state: Partial<PersonalSettingsConfigValue>) => {
  const currentValue = syncManager.get('personalSettings');
  const newValue: PersonalSettingsConfigValue = {
    ...DEFAULT_PERSONAL_SETTINGS,
    ...currentValue,
    ...state,
  };
  syncManager.set('personalSettings', newValue);
};

/**
 * 同步 MCP 配置到后端
 */
const syncMCPServers = (mcpConfigs: MCPServiceConfig[]) => {
  const value: MCPServersConfigValue = { mcpConfigs };
  syncManager.set('mcpServers', value);
};

/**
 * 同步搜索服务配置到后端
 */
const syncSearchServices = (searchServiceConfigs: SearchServiceConfigItem[]) => {
  const value: SearchServicesConfigValue = { searchServiceConfigs };
  syncManager.set('searchServices', value);
};

const useConfigStore = create<ConfigState>()((set, get) => ({
      // ============ 初始状态 ============
      fetchRawWebpage: DEFAULT_PERSONAL_SETTINGS.fetchRawWebpage,
      extractDocumentText: DEFAULT_PERSONAL_SETTINGS.extractDocumentText,
      generateSearchSuggestions: DEFAULT_PERSONAL_SETTINGS.generateSearchSuggestions,
      enableCostEstimation: DEFAULT_PERSONAL_SETTINGS.enableCostEstimation,
      enableCacheBreakNotification: DEFAULT_PERSONAL_SETTINGS.enableCacheBreakNotification,
      showContextUsage: DEFAULT_PERSONAL_SETTINGS.showContextUsage,
      enableMemory: DEFAULT_PERSONAL_SETTINGS.enableMemory,
      memoryRequireConfirmation: DEFAULT_PERSONAL_SETTINGS.memoryRequireConfirmation,
      enableMemoryAutoExtraction: DEFAULT_PERSONAL_SETTINGS.enableMemoryAutoExtraction,
      memoryEnableConversationSearch: DEFAULT_PERSONAL_SETTINGS.memoryEnableConversationSearch,
      preCompactEnabled: DEFAULT_PERSONAL_SETTINGS.preCompactEnabled,
      preCompactBudgetTokens: DEFAULT_PERSONAL_SETTINGS.preCompactBudgetTokens,
      enableAutoTitleGeneration: DEFAULT_PERSONAL_SETTINGS.enableAutoTitleGeneration,
      webTtsProvider: DEFAULT_PERSONAL_SETTINGS.webTtsProvider,
      systemInstructions: DEFAULT_PERSONAL_SETTINGS.systemInstructions,
      timezone: DEFAULT_PERSONAL_SETTINGS.timezone,
      enableWebNotifications: DEFAULT_PERSONAL_SETTINGS.enableWebNotifications,
      enableCompletionSound: DEFAULT_PERSONAL_SETTINGS.enableCompletionSound,
      enableIdleApprovalNotification: DEFAULT_PERSONAL_SETTINGS.enableIdleApprovalNotification,
      approvalNotificationSound: DEFAULT_PERSONAL_SETTINGS.approvalNotificationSound,
      privacyEnabled: false,
      privacyS2Action: 'warn' as const,
      privacyS3Action: 'redact' as const,
      privacyDeepScan: false,
      privacyRouting: {},
      privacyCustomKeywordsS2: [] as string[],
      privacyCustomKeywordsS3: [] as string[],
      privacyCustomPatternsS2: [] as string[],
      privacyCustomPatternsS3: [] as string[],
      privacySensitiveToolsS2: [] as string[],
      privacySensitiveToolsS3: [] as string[],
      codeExecutionAllowNetwork: DEFAULT_PERSONAL_SETTINGS.codeExecutionAllowNetwork ?? true,
      enableEvalLab: DEFAULT_PERSONAL_SETTINGS.enableEvalLab ?? false,
      smoothStreamEnabled: DEFAULT_PERSONAL_SETTINGS.smoothStreamEnabled ?? true,
      suggestWorkflowMode: DEFAULT_PERSONAL_SETTINGS.suggestWorkflowMode ?? true,
      publicIngressBaseUrl: DEFAULT_PERSONAL_SETTINGS.publicIngressBaseUrl ?? '',
      searchServiceConfigs: DEFAULT_SEARCH_SERVICES.searchServiceConfigs,
      mcpConfigs: DEFAULT_MCP_SERVERS.mcpConfigs,
      orgMcpConfigs: [],

      // ============ 基础设置 Actions ============

      setFetchRawWebpage: (fetch) => {
        set({ fetchRawWebpage: fetch });
        syncPersonalSettings({ fetchRawWebpage: fetch });
      },

      setExtractDocumentText: (enabled) => {
        set({ extractDocumentText: enabled });
        syncPersonalSettings({ extractDocumentText: enabled });
      },

      setGenerateSearchSuggestions: (generate) => {
        set({ generateSearchSuggestions: generate });
        syncPersonalSettings({ generateSearchSuggestions: generate });
      },

      setEnableCostEstimation: (enable) => {
        set({ enableCostEstimation: enable });
        syncPersonalSettings({ enableCostEstimation: enable });
      },

      setEnableCacheBreakNotification: (enable) => {
        set({ enableCacheBreakNotification: enable });
        syncPersonalSettings({ enableCacheBreakNotification: enable });
      },

      setShowContextUsage: (show) => {
        set({ showContextUsage: show });
        syncPersonalSettings({ showContextUsage: show });
      },

      setEnableMemory: (enable) => {
        set({ enableMemory: enable });
        syncPersonalSettings({ enableMemory: enable });
      },

      setMemoryRequireConfirmation: (enable) => {
        set({ memoryRequireConfirmation: enable });
        syncPersonalSettings({ memoryRequireConfirmation: enable });
      },

      setEnableMemoryAutoExtraction: (enable) => {
        set({ enableMemoryAutoExtraction: enable });
        syncPersonalSettings({ enableMemoryAutoExtraction: enable });
      },

      setMemoryEnableConversationSearch: (enable) => {
        set({ memoryEnableConversationSearch: enable });
        syncPersonalSettings({ memoryEnableConversationSearch: enable });
      },

      setPreCompactEnabled: (enable) => {
        set({ preCompactEnabled: enable });
        syncPersonalSettings({ preCompactEnabled: enable });
      },

      setPreCompactBudgetTokens: (tokens) => {
        const normalized = Math.max(800, Math.min(tokens, 2000));
        set({ preCompactBudgetTokens: normalized });
        syncPersonalSettings({ preCompactBudgetTokens: normalized });
      },

      setEnableAutoTitleGeneration: (enable) => {
        set({ enableAutoTitleGeneration: enable });
        syncPersonalSettings({ enableAutoTitleGeneration: enable });
      },

      setWebTtsProvider: (provider) => {
        set({ webTtsProvider: provider });
        syncPersonalSettings({ webTtsProvider: provider });
      },

      setCustomPrimaryColor: (color) => {
        set({ customPrimaryColor: color });
        syncPersonalSettings({ customPrimaryColor: color });
      },

      updatePersonalSettings: async (settings) => {
        set((state) => ({
          ...settings,
          personalSettings: {
            ...DEFAULT_PERSONAL_SETTINGS,
            ...state.personalSettings,
            ...settings,
          },
        }));
        syncPersonalSettings(settings);
      },

      setSystemInstructions: (instructions) => {
        set({ systemInstructions: instructions });
        syncPersonalSettings({ systemInstructions: instructions });
      },

      setTimezone: (tz) => {
        set({ timezone: tz });
        syncPersonalSettings({ timezone: tz });
      },

      setEnableWebNotifications: (enable) => {
        set({ enableWebNotifications: enable });
        syncPersonalSettings({ enableWebNotifications: enable });
      },

      setEnableCompletionSound: (enable) => {
        set({ enableCompletionSound: enable });
        syncPersonalSettings({ enableCompletionSound: enable });
      },

      setEnableIdleApprovalNotification: (enable) => {
        set({ enableIdleApprovalNotification: enable });
        syncPersonalSettings({ enableIdleApprovalNotification: enable });
      },

      setApprovalNotificationSound: (enable) => {
        set({ approvalNotificationSound: enable });
        syncPersonalSettings({ approvalNotificationSound: enable });
      },

      setPrivacyEnabled: (enable) => {
        set({ privacyEnabled: enable });
        syncPersonalSettings({ privacyEnabled: enable });
      },

      setPrivacyS2Action: (action) => {
        set({ privacyS2Action: action });
        syncPersonalSettings({ privacyS2Action: action });
      },

      setPrivacyS3Action: (action) => {
        set({ privacyS3Action: action });
        syncPersonalSettings({ privacyS3Action: action });
      },

      setPrivacyDeepScan: (enable) => {
        set({ privacyDeepScan: enable });
        syncPersonalSettings({ privacyDeepScan: enable });
      },

      setPrivacyRouting: (config) => {
        set({ privacyRouting: config });
        syncPersonalSettings({ privacyRouting: config });
      },

      setPrivacyCustomKeywordsS2: (keywords) => {
        set({ privacyCustomKeywordsS2: keywords });
        syncPersonalSettings({ privacyCustomKeywordsS2: keywords });
      },

      setPrivacyCustomKeywordsS3: (keywords) => {
        set({ privacyCustomKeywordsS3: keywords });
        syncPersonalSettings({ privacyCustomKeywordsS3: keywords });
      },

      setPrivacyCustomPatternsS2: (patterns) => {
        set({ privacyCustomPatternsS2: patterns });
        syncPersonalSettings({ privacyCustomPatternsS2: patterns });
      },

      setPrivacyCustomPatternsS3: (patterns) => {
        set({ privacyCustomPatternsS3: patterns });
        syncPersonalSettings({ privacyCustomPatternsS3: patterns });
      },

      setPrivacySensitiveToolsS2: (tools) => {
        set({ privacySensitiveToolsS2: tools });
        syncPersonalSettings({ privacySensitiveToolsS2: tools });
      },

      setPrivacySensitiveToolsS3: (tools) => {
        set({ privacySensitiveToolsS3: tools });
        syncPersonalSettings({ privacySensitiveToolsS3: tools });
      },

      setCodeExecutionAllowNetwork: (allow) => {
        set({ codeExecutionAllowNetwork: allow });
        syncPersonalSettings({ codeExecutionAllowNetwork: allow });
      },

      setEnableEvalLab: (enable) => {
        set({ enableEvalLab: enable });
        syncPersonalSettings({ enableEvalLab: enable });
      },

      setSmoothStreamEnabled: (enable) => {
        set({ smoothStreamEnabled: enable });
        syncPersonalSettings({ smoothStreamEnabled: enable });
      },

      setSuggestWorkflowMode: (enable: boolean) => {
        set({ suggestWorkflowMode: enable });
        syncPersonalSettings({ suggestWorkflowMode: enable });
      },

      setPublicIngressBaseUrl: (url) => {
        const normalized = normalizePublicIngressBaseUrl(url ?? '');
        set({ publicIngressBaseUrl: normalized });
        if (!normalized || isValidPublicIngressBaseUrl(normalized)) {
          syncPersonalSettings({ publicIngressBaseUrl: normalized });
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('ingress-requirement-changed'));
          }
        }
      },

      setNotificationDeliveries: (deliveries) => {
        const current = get().personalSettings;
        const updated = { ...current, notificationDeliveries: deliveries ?? undefined };
        set({
          personalSettings: updated as import('@/services/config/types').PersonalSettingsConfigValue,
        });
        syncPersonalSettings({ notificationDeliveries: deliveries ?? undefined });
      },

      setImageGeneration: (config) => {
        set({ imageGeneration: config });
        syncPersonalSettings({ imageGeneration: config });
      },

      setVideoGeneration: (config) => {
        set({ videoGeneration: config });
        syncPersonalSettings({ videoGeneration: config });
      },

      // ============ MCP 配置管理 ============

      setMCPConfigs: (configs) => {
        const newConfigs = mcpManager.setMCPConfigs(configs);
        set({ mcpConfigs: newConfigs });
        syncMCPServers(newConfigs);
      },

      addMCPConfig: (config) => {
        const state = get();
        const newConfigs = mcpManager.addMCPConfig(state.mcpConfigs, config);
        set({ mcpConfigs: newConfigs });
        syncMCPServers(newConfigs);
      },

      updateMCPConfig: (index, config) => {
        const state = get();
        const newConfigs = mcpManager.updateMCPConfig(state.mcpConfigs, index, config);
        set({ mcpConfigs: newConfigs });
        syncMCPServers(newConfigs);
      },

      removeMCPConfig: (index) => {
        const state = get();
        const newConfigs = mcpManager.removeMCPConfig(state.mcpConfigs, index);
        set({ mcpConfigs: newConfigs });
        syncMCPServers(newConfigs);
      },

      toggleMCPConfig: (index) => {
        const state = get();
        const newConfigs = mcpManager.toggleMCPConfig(state.mcpConfigs, index);
        set({ mcpConfigs: newConfigs });
        syncMCPServers(newConfigs);
      },

      // ============ 搜索服务配置管理 ============

      setSearchServiceConfigs: (configs) => {
        const newConfigs = searchServiceManager.setSearchServiceConfigs(configs);
        set({ searchServiceConfigs: newConfigs });
        syncSearchServices(newConfigs);
        invalidateLocalCapabilitiesProbeCache();
      },

      addSearchServiceConfig: (config) => {
        const state = get();
        const newConfigs = searchServiceManager.addSearchServiceConfig(state.searchServiceConfigs, config);
        set({ searchServiceConfigs: newConfigs });
        syncSearchServices(newConfigs);
        invalidateLocalCapabilitiesProbeCache();
      },

      updateSearchServiceConfig: (id, updates) => {
        const state = get();
        const newConfigs = searchServiceManager.updateSearchServiceConfig(state.searchServiceConfigs, id, updates);
        set({ searchServiceConfigs: newConfigs });
        syncSearchServices(newConfigs);
        invalidateLocalCapabilitiesProbeCache();
      },

      removeSearchServiceConfig: (id) => {
        const state = get();
        const newConfigs = searchServiceManager.removeSearchServiceConfig(state.searchServiceConfigs, id);
        set({ searchServiceConfigs: newConfigs });
        syncSearchServices(newConfigs);
        invalidateLocalCapabilitiesProbeCache();
      },

      enableSearchServiceConfig: (id) => {
        const state = get();
        const newConfigs = searchServiceManager.enableSearchServiceConfig(state.searchServiceConfigs, id);
        set({ searchServiceConfigs: newConfigs });
        syncSearchServices(newConfigs);
        invalidateLocalCapabilitiesProbeCache();
      },

      getActiveSearchServiceConfig: () => {
        const state = get();
        return searchServiceManager.getActiveSearchServiceConfig(state.searchServiceConfigs);
      },

      // ============ 导入导出 ============

      exportConfig: () => {
        const state = get();
        return importExportManager.exportConfig(state);
      },

      importConfig: async (configJson) => {
        const state = get();
        return importExportManager.importConfig(configJson, {
          setSystemInstructions: state.setSystemInstructions,
          setFetchRawWebpage: state.setFetchRawWebpage,
          setExtractDocumentText: state.setExtractDocumentText,
          setGenerateSearchSuggestions: state.setGenerateSearchSuggestions,
          setEnableCostEstimation: state.setEnableCostEstimation,
          setSearchServiceConfigs: state.setSearchServiceConfigs,
          setMCPConfigs: state.setMCPConfigs,
        });
      },

      // ============ 初始化 ============

      initConfig: async () => {
        // 防止重复初始化（使用 store 内部标志，而非 syncManager.isInitialized）
        if (get()._configStoreReady) {
          console.log('[ConfigStore] Already initialized, skipping');
          return;
        }

        try {
          // syncManager 可能已由 SettingsSyncInitializer 初始化
          if (!syncManager.isInitialized) {
            await syncManager.initialize();
          }

          set({ _configStoreReady: true });

          // 应用后端配置到 Store
          const personalSettings = syncManager.get('personalSettings');
          const mcpServers = syncManager.get('mcpServers');
          const orgMcpServers = syncManager.get('orgMcpServers') as { servers?: MCPServiceConfig[] } | null;
          const searchServices = syncManager.get('searchServices');

          const migratedPersonal = normalizePersonalSettings(personalSettings);

          const rawSearchConfigs = searchServices?.searchServiceConfigs ?? [];
          const validatedSearchConfigs = rawSearchConfigs.map((c: SearchServiceConfigItem) => ({
            ...c,
            role: c.role || 'primary',
          }));

          const orgConfigs: MCPServiceConfig[] = (orgMcpServers?.servers ?? []).map((s) => ({
            ...s,
            enabled: true,
            description: s.description || '',
            extra_params: { ...s.extra_params, scope: 'org' },
          })) as MCPServiceConfig[];

          set({
            ...migratedPersonal,
            personalSettings: migratedPersonal,
            mcpConfigs: mcpServers?.mcpConfigs ?? [],
            orgMcpConfigs: orgConfigs,
            searchServiceConfigs: validatedSearchConfigs,
          });

          syncManager.subscribe('personalSettings', (_key, value) => {
            set({
              ...(value as PersonalSettingsConfigValue),
              personalSettings: value as PersonalSettingsConfigValue,
            });
          });

          syncManager.subscribe('mcpServers', (_key, value) => {
            const v = value as MCPServersConfigValue;
            set({ mcpConfigs: v.mcpConfigs });
          });

          syncManager.subscribe('orgMcpServers', (_key, value) => {
            const v = value as { servers?: MCPServiceConfig[] } | null;
            const configs: MCPServiceConfig[] = (v?.servers ?? []).map((s) => ({
              ...s,
              enabled: true,
              description: s.description || '',
              extra_params: { ...s.extra_params, scope: 'org' },
            })) as MCPServiceConfig[];
            set({ orgMcpConfigs: configs });
          });

          syncManager.subscribe('searchServices', (_key, value) => {
            const v = value as SearchServicesConfigValue;
            set({ searchServiceConfigs: v.searchServiceConfigs });
          });

          console.log('[ConfigStore] Initialized from backend');
        } catch (error) {
          console.warn('[ConfigStore] Failed to initialize from backend, using local state:', error);
        }
      },

      // ============ 验证方法 ============

      validateSearchServiceConfig: async (config: SearchServiceConfig) => {
        return validation.validateSearchServiceConfig(config);
      },

      validateMCPConfig: async (config: MCPServiceConfig) => {
        return validation.validateMCPConfig(config);
      },
    }),
);

export default useConfigStore;

// 重新导出类型
export type {
  ConfigState,
  MCPOAuthSettings,
  MCPServiceConfig,
  SearchServiceConfig,
  SearchServiceConfigItem,
  ValidationResult,
} from './config/types';
