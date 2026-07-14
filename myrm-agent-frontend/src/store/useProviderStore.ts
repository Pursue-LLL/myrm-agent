/**
 * Provider Store - 管理模型服务商配置
 *
 * 存储策略（统一使用 ConfigSyncManager）：
 * - Tauri 模式（Desktop/WebUI）：同步到本地 SQLite（明文存储）
 * - Sandbox 模式：同步到云端 PostgreSQL（服务端加密）
 * - 访客模式：仅保存到 localStorage，不同步
 *
 * 数据流：
 * 1. 初始化时从 ConfigSyncManager 加载
 * 2. 修改时乐观更新本地状态 + 通知 ConfigSyncManager
 * 3. ConfigSyncManager 负责防抖同步到后端
 */

import { create } from 'zustand';
import {
  ProviderConfig,
  DefaultModelConfig,
  ApiKeyConfig,
  SingleModelSelection,
  CustomModelInfo,
  CustomProviderType,
  CUSTOM_PROVIDER_TYPE_INFO,
  getInitialProviders,
  getInitialDefaultModelConfig,
} from './config/providerTypes';
import { normalizeProviders } from '@/services/config/configNormalizer';
import { getConfigSyncManager, type ProvidersConfigValue } from '@/services/config';
import { ensureLocalBackendReady } from '@/lib/backend-health';
import { isLocalMode } from '@/lib/deploy-mode';
import { ensurePlatformReadiness } from '@/lib/platform-readiness';

// 初始化标志
let isStoreInitialized = false;
let providersSubscribeRegistered = false;

interface ProviderState {
  // 提供商列表
  providers: ProviderConfig[];
  // 默认模型配置
  defaultModelConfig: DefaultModelConfig;
  // 自定义模型信息（key 格式：providerId/model）
  customModelInfo: Record<string, CustomModelInfo>;
  // 是否已初始化
  isInitialized: boolean;
  // 初始化失败时的错误信息
  initError: string | null;

  // 初始化
  initProviders: () => Promise<void>;
  // 重试初始化（用户手动触发）
  retryInit: () => Promise<void>;

  // 提供商操作
  setProviders: (providers: ProviderConfig[]) => void;
  addProvider: (name: string, providerType: CustomProviderType) => void;
  removeProvider: (id: string) => void;
  updateProvider: (id: string, updates: Partial<ProviderConfig>) => void;
  setProviderEnabled: (id: string, enabled: boolean) => void;

  // API 密钥操作
  addApiKey: (providerId: string, key: string, remark: string) => void;
  removeApiKey: (providerId: string, keyId: string) => void;
  setActiveApiKey: (providerId: string, keyId: string) => void;
  updateApiKeyRemark: (providerId: string, keyId: string, remark: string) => void;

  // 模型操作
  setEnabledModels: (providerId: string, models: string[]) => void;
  setAvailableModels: (providerId: string, models: string[]) => void;

  // 默认模型配置
  setDefaultModelConfig: (config: DefaultModelConfig) => void;
  setBaseModel: (selection: SingleModelSelection | null) => void;
  setBaseModelFallback: (selection: SingleModelSelection | null) => void;
  setLiteModel: (selection: SingleModelSelection | null) => void;
  setLiteModelFallback: (selection: SingleModelSelection | null) => void;
  setBaseModelTemperature: (temperature: number) => void;
  setBaseModelKwargs: (kwargs: Record<string, unknown>) => void;
  setLiteModelKwargs: (kwargs: Record<string, unknown>) => void;
  setFastModeModel: (selection: SingleModelSelection | null) => void;
  setRoutingEnabled: (enabled: boolean) => void;
  setRoutingLightModel: (selection: SingleModelSelection | null) => void;
  setRoutingLightModelFallback: (selection: SingleModelSelection | null) => void;
  setRoutingReasoningModel: (selection: SingleModelSelection | null) => void;
  setRoutingReasoningModelFallback: (selection: SingleModelSelection | null) => void;
  setVisionFallbackModel: (selection: SingleModelSelection | null) => void;

  // 自定义模型信息操作
  getModelInfo: (providerId: string, model: string) => CustomModelInfo | undefined;
  setModelInfo: (providerId: string, model: string, info: CustomModelInfo) => void;
  setCustomModelInfo: (info: Record<string, CustomModelInfo>) => void;
  removeModelInfo: (providerId: string, model: string) => void;

  // 获取已启用的模型（用于默认模型选择）
  getEnabledModels: () => Array<{ providerId: string; providerName: string; model: string }>;
}

function syncToManager(
  providers: ProviderConfig[],
  defaultModelConfig: DefaultModelConfig,
  customModelInfo: Record<string, CustomModelInfo>,
): void {
  const value = normalizeProviders({ providers, defaultModelConfig, customModelInfo });
  getConfigSyncManager().set('providers', value);
}

function hydrateFromProvidersValue(configValue: ProvidersConfigValue): Pick<
  ProviderState,
  'providers' | 'defaultModelConfig' | 'customModelInfo'
> {
  const normalized = normalizeProviders(configValue);
  return {
    providers: normalized.providers,
    defaultModelConfig: normalized.defaultModelConfig,
    customModelInfo: normalized.customModelInfo || {},
  };
}

const useProviderStore = create<ProviderState>((set, get) => ({
  providers: [],
  defaultModelConfig: getInitialDefaultModelConfig(),
  customModelInfo: {},
  isInitialized: false,
  initError: null,

  initProviders: async () => {
    if (isStoreInitialized) return;

    try {
      if (typeof window !== 'undefined' && isLocalMode()) {
        await ensureLocalBackendReady();
      }

      const manager = getConfigSyncManager();
      await manager.initialize();

      const configValue = manager.get('providers');
      if (configValue) {
        set({
          ...hydrateFromProvidersValue(configValue as ProvidersConfigValue),
          isInitialized: true,
          initError: null,
        });
      } else if (manager.status === 'offline') {
        set({
          providers: getInitialProviders(),
          defaultModelConfig: getInitialDefaultModelConfig(),
          customModelInfo: {},
          isInitialized: false,
          initError: 'Backend offline during config load',
        });
        if (!providersSubscribeRegistered) {
          manager.subscribe('providers', (_key, value) => {
            set({
              ...hydrateFromProvidersValue(value as ProvidersConfigValue),
              isInitialized: true,
              initError: null,
            });
            isStoreInitialized = true;
          });
          providersSubscribeRegistered = true;
        }
        void ensurePlatformReadiness().then((snapshot) => {
          if (snapshot.database) {
            void get().initProviders();
          }
        });
        return;
      } else {
        set({
          providers: getInitialProviders(),
          defaultModelConfig: getInitialDefaultModelConfig(),
          customModelInfo: {},
          isInitialized: true,
          initError: null,
        });
      }

      if (!providersSubscribeRegistered) {
        manager.subscribe('providers', (_key, value) => {
          set(hydrateFromProvidersValue(value as ProvidersConfigValue));
        });
        providersSubscribeRegistered = true;
      }

      isStoreInitialized = true;
      console.log('[ProviderStore] Initialized from ConfigSyncManager');
    } catch (error) {
      console.error('[ProviderStore] Initialization failed:', error);
      const message = error instanceof Error ? error.message : 'Unknown error';
      set({
        isInitialized: true,
        initError: message,
      });
    }
  },

  retryInit: async () => {
    isStoreInitialized = false;
    set({ isInitialized: false, initError: null });
    await get().initProviders();
  },

  setProviders: (providers) => {
    const { defaultModelConfig, customModelInfo } = get();
    const normalized = normalizeProviders({ providers, defaultModelConfig, customModelInfo });
    syncToManager(normalized.providers, normalized.defaultModelConfig, normalized.customModelInfo);
    set({
      providers: normalized.providers,
      defaultModelConfig: normalized.defaultModelConfig,
      customModelInfo: normalized.customModelInfo,
    });
  },

  addProvider: (name, providerType) => {
    const id = name.toLowerCase().replace(/\s+/g, '_');
    const newProvider: ProviderConfig = {
      id,
      name,
      isBuiltIn: false,
      isEnabled: false,
      apiKeys: [],
      apiUrl: '',
      enabledModels: [],
      availableModels: [],
      providerType,
      routingProfile: CUSTOM_PROVIDER_TYPE_INFO[providerType].litellmPrefix,
    };
    const providers = [...get().providers, newProvider];
    const { defaultModelConfig, customModelInfo } = get();
    syncToManager(providers, defaultModelConfig, customModelInfo);
    set({ providers });
  },

  removeProvider: (id) => {
    const providers = get().providers.filter((p) => p.id !== id);

    // 清理该提供商下所有模型的自定义信息
    const customModelInfo = { ...get().customModelInfo };
    const keysToDelete = Object.keys(customModelInfo).filter((key) => key.startsWith(`${id}/`));
    for (const key of keysToDelete) {
      delete customModelInfo[key];
    }

    let defaultModelConfig = { ...get().defaultModelConfig };
    if (defaultModelConfig.baseModel.primary?.providerId === id) {
      defaultModelConfig = {
        ...defaultModelConfig,
        baseModel: { ...defaultModelConfig.baseModel, primary: null },
      };
    }
    if (defaultModelConfig.baseModel.fallback?.providerId === id) {
      defaultModelConfig = {
        ...defaultModelConfig,
        baseModel: { ...defaultModelConfig.baseModel, fallback: null },
      };
    }
    if (defaultModelConfig.liteModel.primary?.providerId === id) {
      defaultModelConfig = {
        ...defaultModelConfig,
        liteModel: { ...defaultModelConfig.liteModel, primary: null },
      };
    }
    if (defaultModelConfig.liteModel.fallback?.providerId === id) {
      defaultModelConfig = {
        ...defaultModelConfig,
        liteModel: { ...defaultModelConfig.liteModel, fallback: null },
      };
    }
    if (defaultModelConfig.visionFallbackModel?.providerId === id) {
      defaultModelConfig = {
        ...defaultModelConfig,
        visionFallbackModel: null,
      };
    }

    syncToManager(providers, defaultModelConfig, customModelInfo);
    set({ providers, defaultModelConfig, customModelInfo });
  },

  updateProvider: (id, updates) => {
    const providers = get().providers.map((p) => (p.id === id ? { ...p, ...updates } : p));
    const { defaultModelConfig, customModelInfo } = get();
    syncToManager(providers, defaultModelConfig, customModelInfo);
    set({ providers });
  },

  setProviderEnabled: (id, enabled) => {
    const providers = get().providers.map((p) => (p.id === id ? { ...p, isEnabled: enabled } : p));

    let defaultModelConfig = get().defaultModelConfig;
    if (!enabled) {
      const newConfig = { ...defaultModelConfig };
      if (newConfig.baseModel.primary?.providerId === id) {
        newConfig.baseModel = { ...newConfig.baseModel, primary: null };
      }
      if (newConfig.baseModel.fallback?.providerId === id) {
        newConfig.baseModel = { ...newConfig.baseModel, fallback: null };
      }
      if (newConfig.liteModel.primary?.providerId === id) {
        newConfig.liteModel = { ...newConfig.liteModel, primary: null };
      }
      if (newConfig.liteModel.fallback?.providerId === id) {
        newConfig.liteModel = { ...newConfig.liteModel, fallback: null };
      }
      if (newConfig.visionFallbackModel?.providerId === id) {
        newConfig.visionFallbackModel = null;
      }
      defaultModelConfig = newConfig;
    }

    const { customModelInfo } = get();
    syncToManager(providers, defaultModelConfig, customModelInfo);
    set({ providers, defaultModelConfig });
  },

  addApiKey: (providerId, key, remark) => {
    const providers = get().providers.map((p) => {
      if (p.id !== providerId) return p;
      const newKey: ApiKeyConfig = {
        id: `key_${Date.now()}`,
        key,
        remark: remark || '默认密钥',
        isActive: p.apiKeys.length === 0,
      };
      return {
        ...p,
        isEnabled: true,
        apiKeys: [...p.apiKeys, newKey],
      };
    });
    const { defaultModelConfig, customModelInfo } = get();
    syncToManager(providers, defaultModelConfig, customModelInfo);
    set({ providers });
  },

  removeApiKey: (providerId, keyId) => {
    const providers = get().providers.map((p) => {
      if (p.id !== providerId) return p;
      const apiKeys = p.apiKeys.filter((k) => k.id !== keyId);
      if (apiKeys.length > 0 && !apiKeys.some((k) => k.isActive)) {
        apiKeys[0].isActive = true;
      }
      return { ...p, apiKeys };
    });
    const { defaultModelConfig, customModelInfo } = get();
    syncToManager(providers, defaultModelConfig, customModelInfo);
    set({ providers });
  },

  setActiveApiKey: (providerId, keyId) => {
    const providers = get().providers.map((p) => {
      if (p.id !== providerId) return p;
      return { ...p, apiKeys: p.apiKeys.map((k) => ({ ...k, isActive: k.id === keyId })) };
    });
    const { defaultModelConfig, customModelInfo } = get();
    syncToManager(providers, defaultModelConfig, customModelInfo);
    set({ providers });
  },

  updateApiKeyRemark: (providerId, keyId, remark) => {
    const providers = get().providers.map((p) => {
      if (p.id !== providerId) return p;
      return { ...p, apiKeys: p.apiKeys.map((k) => (k.id === keyId ? { ...k, remark } : k)) };
    });
    const { defaultModelConfig, customModelInfo } = get();
    syncToManager(providers, defaultModelConfig, customModelInfo);
    set({ providers });
  },

  setEnabledModels: (providerId, models) => {
    const providers = get().providers.map((p) => (p.id === providerId ? { ...p, enabledModels: models } : p));
    const { defaultModelConfig, customModelInfo } = get();
    syncToManager(providers, defaultModelConfig, customModelInfo);
    set({ providers });
  },

  setAvailableModels: (providerId, models) => {
    const providers = get().providers.map((p) => (p.id === providerId ? { ...p, availableModels: models } : p));
    const { defaultModelConfig, customModelInfo } = get();
    syncToManager(providers, defaultModelConfig, customModelInfo);
    set({ providers });
  },

  setDefaultModelConfig: (config) => {
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  setBaseModel: (selection) => {
    const config = {
      ...get().defaultModelConfig,
      baseModel: { ...get().defaultModelConfig.baseModel, primary: selection },
    };
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  setBaseModelFallback: (selection) => {
    const config = {
      ...get().defaultModelConfig,
      baseModel: { ...get().defaultModelConfig.baseModel, fallback: selection },
    };
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  setLiteModel: (selection) => {
    const config = {
      ...get().defaultModelConfig,
      liteModel: { ...get().defaultModelConfig.liteModel, primary: selection },
    };
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  setLiteModelFallback: (selection) => {
    const config = {
      ...get().defaultModelConfig,
      liteModel: { ...get().defaultModelConfig.liteModel, fallback: selection },
    };
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  setBaseModelTemperature: (temperature) => {
    const config = {
      ...get().defaultModelConfig,
      baseModel: { ...get().defaultModelConfig.baseModel, temperature },
    };
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  setBaseModelKwargs: (kwargs) => {
    const config = {
      ...get().defaultModelConfig,
      baseModel: { ...get().defaultModelConfig.baseModel, modelKwargs: kwargs },
    };
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  setLiteModelKwargs: (kwargs) => {
    const config = {
      ...get().defaultModelConfig,
      liteModel: { ...get().defaultModelConfig.liteModel, modelKwargs: kwargs },
    };
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  setFastModeModel: (selection) => {
    const current = get().defaultModelConfig;
    const config: DefaultModelConfig = {
      ...current,
      fastModeModel: selection
        ? {
            primary: selection,
            fallback: null,
            temperature: current.baseModel.temperature,
            modelKwargs: current.baseModel.modelKwargs,
          }
        : null,
    };
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  setRoutingEnabled: (enabled) => {
    const current = get().defaultModelConfig;
    const existing = current.routingConfig;
    const emptySlot = { primary: null, fallback: null };
    const config: DefaultModelConfig = {
      ...current,
      routingConfig: {
        enabled,
        lightModel: existing?.lightModel ?? emptySlot,
        reasoningModel: existing?.reasoningModel ?? emptySlot,
      },
    };
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  setRoutingLightModel: (selection) => {
    const current = get().defaultModelConfig;
    const existing = current.routingConfig;
    const emptySlot = { primary: null, fallback: null };
    const config: DefaultModelConfig = {
      ...current,
      routingConfig: {
        enabled: existing?.enabled ?? false,
        lightModel: { ...(existing?.lightModel ?? emptySlot), primary: selection },
        reasoningModel: existing?.reasoningModel ?? emptySlot,
      },
    };
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  setRoutingLightModelFallback: (selection) => {
    const current = get().defaultModelConfig;
    const existing = current.routingConfig;
    const emptySlot = { primary: null, fallback: null };
    const config: DefaultModelConfig = {
      ...current,
      routingConfig: {
        enabled: existing?.enabled ?? false,
        lightModel: { ...(existing?.lightModel ?? emptySlot), fallback: selection },
        reasoningModel: existing?.reasoningModel ?? emptySlot,
      },
    };
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  setRoutingReasoningModel: (selection) => {
    const current = get().defaultModelConfig;
    const existing = current.routingConfig;
    const emptySlot = { primary: null, fallback: null };
    const config: DefaultModelConfig = {
      ...current,
      routingConfig: {
        enabled: existing?.enabled ?? false,
        lightModel: existing?.lightModel ?? emptySlot,
        reasoningModel: { ...(existing?.reasoningModel ?? emptySlot), primary: selection },
      },
    };
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  setRoutingReasoningModelFallback: (selection) => {
    const current = get().defaultModelConfig;
    const existing = current.routingConfig;
    const emptySlot = { primary: null, fallback: null };
    const config: DefaultModelConfig = {
      ...current,
      routingConfig: {
        enabled: existing?.enabled ?? false,
        lightModel: existing?.lightModel ?? emptySlot,
        reasoningModel: { ...(existing?.reasoningModel ?? emptySlot), fallback: selection },
      },
    };
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  setVisionFallbackModel: (selection) => {
    const config = {
      ...get().defaultModelConfig,
      visionFallbackModel: selection,
    };
    const { providers, customModelInfo } = get();
    syncToManager(providers, config, customModelInfo);
    set({ defaultModelConfig: config });
  },

  getModelInfo: (providerId, model) => {
    const key = `${providerId}/${model}`;
    return get().customModelInfo[key];
  },

  setModelInfo: (providerId, model, info) => {
    const key = `${providerId}/${model}`;
    const customModelInfo = { ...get().customModelInfo, [key]: info };
    const { providers, defaultModelConfig } = get();
    syncToManager(providers, defaultModelConfig, customModelInfo);
    set({ customModelInfo });
  },

  setCustomModelInfo: (info) => {
    const { providers, defaultModelConfig } = get();
    syncToManager(providers, defaultModelConfig, info);
    set({ customModelInfo: info });
  },

  removeModelInfo: (providerId, model) => {
    const key = `${providerId}/${model}`;
    const customModelInfo = { ...get().customModelInfo };
    delete customModelInfo[key];

    let defaultModelConfig = { ...get().defaultModelConfig };
    const isMatch = (s: SingleModelSelection | null) => s?.providerId === providerId && s?.model === model;

    if (isMatch(defaultModelConfig.baseModel.primary)) {
      defaultModelConfig = {
        ...defaultModelConfig,
        baseModel: { ...defaultModelConfig.baseModel, primary: null },
      };
    }
    if (isMatch(defaultModelConfig.baseModel.fallback)) {
      defaultModelConfig = {
        ...defaultModelConfig,
        baseModel: { ...defaultModelConfig.baseModel, fallback: null },
      };
    }
    if (isMatch(defaultModelConfig.liteModel.primary)) {
      defaultModelConfig = {
        ...defaultModelConfig,
        liteModel: { ...defaultModelConfig.liteModel, primary: null },
      };
    }
    if (isMatch(defaultModelConfig.liteModel.fallback)) {
      defaultModelConfig = {
        ...defaultModelConfig,
        liteModel: { ...defaultModelConfig.liteModel, fallback: null },
      };
    }
    if (isMatch(defaultModelConfig.visionFallbackModel)) {
      defaultModelConfig = {
        ...defaultModelConfig,
        visionFallbackModel: null,
      };
    }
    if (defaultModelConfig.routingConfig) {
      let rc = defaultModelConfig.routingConfig;
      if (isMatch(rc.lightModel.primary)) {
        rc = { ...rc, lightModel: { ...rc.lightModel, primary: null } };
      }
      if (isMatch(rc.lightModel.fallback)) {
        rc = { ...rc, lightModel: { ...rc.lightModel, fallback: null } };
      }
      if (isMatch(rc.reasoningModel.primary)) {
        rc = { ...rc, reasoningModel: { ...rc.reasoningModel, primary: null } };
      }
      if (isMatch(rc.reasoningModel.fallback)) {
        rc = { ...rc, reasoningModel: { ...rc.reasoningModel, fallback: null } };
      }
      if (rc !== defaultModelConfig.routingConfig) {
        defaultModelConfig = { ...defaultModelConfig, routingConfig: rc };
      }
    }

    const { providers } = get();
    syncToManager(providers, defaultModelConfig, customModelInfo);
    set({ customModelInfo, defaultModelConfig });
  },

  getEnabledModels: () => {
    const providers = get().providers;
    const result: Array<{ providerId: string; providerName: string; model: string }> = [];

    for (const provider of providers) {
      if (!provider.isEnabled) continue;
      if (!provider.apiKeys?.some((k) => k.isActive && k.key)) continue;

      for (const model of provider.enabledModels || []) {
        result.push({
          providerId: provider.id,
          providerName: provider.name,
          model,
        });
      }
    }

    return result;
  },
}));

export default useProviderStore;
