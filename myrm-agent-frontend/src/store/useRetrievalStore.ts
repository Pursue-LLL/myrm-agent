/**
 * Retrieval Store - 管理 Embedding 和 Reranker 配置
 *
 * 存储策略（统一使用 ConfigSyncManager）：
 * - Tauri 模式（Desktop/WebUI）：同步到本地 SQLite（明文存储）
 * - Sandbox 模式：同步到云端 PostgreSQL（服务端加密）
 * - 访客模式：仅保存到 localStorage，不同步
 *
 * 数据流：
 * 1. 初始化时从 ConfigSyncManager 加载
 * 2. 应用成功后通知 ConfigSyncManager 同步
 * 3. ConfigSyncManager 负责防抖同步到后端
 */

import { create } from 'zustand';
import { getConfigSyncManager, type RetrievalConfigValue } from '@/services/config';
import { toLiteLLMFormat, EMBEDDING_PROVIDERS, RERANKER_PROVIDERS } from '@/lib/search/retrievalProviders';

export type ApplyStatus = 'idle' | 'applying' | 'success' | 'error';

export interface ProviderModelConfig {
  provider: string;
  model: string;
  apiKey: string;
  apiBase?: string;
}

export interface RetrievalConfig {
  // Embedding 配置（临时编辑状态）
  embeddingConfig: ProviderModelConfig;
  embeddingApplied: boolean;
  embeddingAppliedAt?: number;
  embeddingApplyStatus: ApplyStatus;
  embeddingApplyMessage?: string;

  // Reranker 配置（临时编辑状态）
  rerankerConfig: ProviderModelConfig;
  rerankerApplied: boolean;
  rerankerAppliedAt?: number;
  rerankerApplyStatus: ApplyStatus;
  rerankerApplyMessage?: string;

  // 高级检索开关（控制网络搜索重排序 + 网页抓取嵌入+重排序）
  enableAdvancedRetrieval: boolean;

  // Orphan collection 状态（模型切换后的旧记忆检测）
  orphanCount: number;
  orphanOldModels: string[];
}

interface RetrievalActions {
  // 初始化
  initRetrieval: () => Promise<void>;

  // Embedding 配置
  setEmbeddingConfig: (config: ProviderModelConfig) => void;
  applyEmbedding: () => Promise<{ success: boolean; message: string }>;
  resetEmbeddingToApplied: () => void;

  // Reranker 配置
  setRerankerConfig: (config: ProviderModelConfig) => void;
  applyReranker: () => Promise<{ success: boolean; message: string }>;
  resetRerankerToApplied: () => void;

  // 高级检索开关
  setEnableAdvancedRetrieval: (enable: boolean) => void;

  // Orphan 重建
  checkOrphanCollections: () => Promise<void>;
  executeReindex: () => Promise<{ migrated: number; failed: number }>;
  dismissOrphanWarning: () => void;

  // 重置所有配置
  reset: () => void;
}

type RetrievalStore = RetrievalConfig & RetrievalActions & { isInitialized: boolean };

const DEFAULT_CONFIG: RetrievalConfig = {
  embeddingConfig: {
    provider: 'siliconflow',
    model: 'BAAI/bge-m3',
    apiKey: '',
    apiBase: '',
  },
  embeddingApplied: false,
  embeddingAppliedAt: undefined,
  embeddingApplyStatus: 'idle',
  embeddingApplyMessage: undefined,
  rerankerConfig: {
    provider: 'siliconflow',
    model: 'BAAI/bge-reranker-v2-m3',
    apiKey: '',
    apiBase: '',
  },
  rerankerApplied: false,
  rerankerAppliedAt: undefined,
  rerankerApplyStatus: 'idle',
  rerankerApplyMessage: undefined,
  enableAdvancedRetrieval: false,
  orphanCount: 0,
  orphanOldModels: [],
};

// 初始化标志
let isStoreInitialized = false;

/**
 * 同步到 ConfigSyncManager
 *
 * 统一通过 ConfigSyncManager 同步：
 * - Tauri 模式：TauriAdapter -> SQLite
 * - Sandbox 模式：SandboxAdapter -> PostgreSQL + 服务端加密
 */
function syncToManager(config: RetrievalConfig): void {
  const value: RetrievalConfigValue = {
    embeddingConfig: config.embeddingConfig,
    embeddingApplied: config.embeddingApplied,
    embeddingAppliedAt: config.embeddingAppliedAt,
    rerankerConfig: config.rerankerConfig,
    rerankerApplied: config.rerankerApplied,
    rerankerAppliedAt: config.rerankerAppliedAt,
    enableAdvancedRetrieval: config.enableAdvancedRetrieval,
  };
  getConfigSyncManager().set('retrieval', value);
}

export const useRetrievalStore = create<RetrievalStore>()((set, get) => ({
      ...DEFAULT_CONFIG,
      isInitialized: false,

      initRetrieval: async () => {
        if (isStoreInitialized) return;

        try {
          // 从 ConfigSyncManager 加载
          const manager = getConfigSyncManager();
          await manager.initialize();

          const configValue = manager.get('retrieval');
          if (configValue) {
            set({
              embeddingConfig: configValue.embeddingConfig ?? DEFAULT_CONFIG.embeddingConfig,
              embeddingApplied: configValue.embeddingApplied ?? false,
              embeddingAppliedAt: configValue.embeddingAppliedAt,
              rerankerConfig: configValue.rerankerConfig ?? DEFAULT_CONFIG.rerankerConfig,
              rerankerApplied: configValue.rerankerApplied ?? false,
              rerankerAppliedAt: configValue.rerankerAppliedAt,
              enableAdvancedRetrieval: configValue.enableAdvancedRetrieval ?? false,
              isInitialized: true,
            });
          } else {
            set({ isInitialized: true });
          }

          // 订阅变更（处理其他设备的同步）
          manager.subscribe('retrieval', (_key, value) => {
            const v = value as RetrievalConfigValue;
            set({
              embeddingConfig: v.embeddingConfig ?? DEFAULT_CONFIG.embeddingConfig,
              embeddingApplied: v.embeddingApplied ?? false,
              embeddingAppliedAt: v.embeddingAppliedAt,
              rerankerConfig: v.rerankerConfig ?? DEFAULT_CONFIG.rerankerConfig,
              rerankerApplied: v.rerankerApplied ?? false,
              rerankerAppliedAt: v.rerankerAppliedAt,
              enableAdvancedRetrieval: v.enableAdvancedRetrieval ?? false,
            });
          });

          isStoreInitialized = true;
          console.log('[RetrievalStore] Initialized from ConfigSyncManager');
        } catch (error) {
          console.error('[RetrievalStore] Initialization failed:', error);
          set({ isInitialized: true });
          isStoreInitialized = true;
        }
      },

      // ============ Embedding 配置 ============

      setEmbeddingConfig: (config) => {
        set({
          embeddingConfig: config,
          embeddingApplyStatus: 'idle',
          embeddingApplyMessage: undefined,
        });
        // 注意：不同步到后端，只有应用成功后才同步
      },

      applyEmbedding: async () => {
        const config = get().embeddingConfig;

        set({ embeddingApplyStatus: 'applying', embeddingApplyMessage: undefined });

        try {
          if (!config.provider || !config.model || !config.apiKey) {
            throw new Error('Missing required fields');
          }

          const litellmModel = toLiteLLMFormat(config.provider, config.model);
          const providerConfig = EMBEDDING_PROVIDERS.find((p) => p.id === config.provider);
          const apiBase = config.apiBase || providerConfig?.defaultApiBase || null;

          const response = await fetch('/api/retrieval/validate/embedding', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              model: litellmModel,
              api_key: config.apiKey,
              api_base: apiBase,
              provider: config.provider,
            }),
          });

          const result = await response.json();

          if (response.ok && result.success) {
            const now = Date.now();

            set({
              embeddingApplied: true,
              embeddingAppliedAt: now,
              embeddingApplyStatus: 'success',
              embeddingApplyMessage: result.message,
            });

            syncToManager(get());

            get().checkOrphanCollections().catch(() => {});

            return { success: true, message: result.message };
          } else {
            throw new Error(result.message || 'Validation failed');
          }
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Network error';

          set({
            embeddingApplyStatus: 'error',
            embeddingApplyMessage: message,
          });

          return { success: false, message };
        }
      },

      resetEmbeddingToApplied: () => {
        set({
          embeddingApplyStatus: 'idle',
          embeddingApplyMessage: undefined,
        });
      },

      // ============ Reranker 配置 ============

      setRerankerConfig: (config) => {
        set({
          rerankerConfig: config,
          rerankerApplyStatus: 'idle',
          rerankerApplyMessage: undefined,
        });
      },

      applyReranker: async () => {
        const config = get().rerankerConfig;

        set({ rerankerApplyStatus: 'applying', rerankerApplyMessage: undefined });

        try {
          if (!config.provider || !config.model || !config.apiKey) {
            throw new Error('Missing required fields');
          }

          const litellmModel = toLiteLLMFormat(config.provider, config.model);
          const providerConfig = RERANKER_PROVIDERS.find((p) => p.id === config.provider);
          const apiBase = config.apiBase || providerConfig?.defaultApiBase || null;

          const response = await fetch('/api/retrieval/validate/reranker', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              model: litellmModel,
              api_key: config.apiKey,
              api_base: apiBase,
              provider: config.provider,
            }),
          });

          const result = await response.json();

          if (response.ok && result.success) {
            const now = Date.now();

            set({
              rerankerApplied: true,
              rerankerAppliedAt: now,
              rerankerApplyStatus: 'success',
              rerankerApplyMessage: result.message,
            });

            // 同步到后端
            syncToManager(get());

            return { success: true, message: result.message };
          } else {
            throw new Error(result.message || 'Validation failed');
          }
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Network error';

          set({
            rerankerApplyStatus: 'error',
            rerankerApplyMessage: message,
          });

          return { success: false, message };
        }
      },

      resetRerankerToApplied: () => {
        set({
          rerankerApplyStatus: 'idle',
          rerankerApplyMessage: undefined,
        });
      },

      // ============ 高级检索开关 ============

      setEnableAdvancedRetrieval: (enable: boolean) => {
        set({ enableAdvancedRetrieval: enable });
        syncToManager(get());
      },

      // ============ Orphan 重建 ============

      checkOrphanCollections: async () => {
        try {
          const response = await fetch('/api/memory/reindex/estimate');
          if (!response.ok) return;
          const data = await response.json();
          const models = (data.orphan_collections ?? []).map(
            (c: { old_model_suffix: string }) => c.old_model_suffix,
          );
          const uniqueModels = [...new Set<string>(models)];
          set({ orphanCount: data.total_memories ?? 0, orphanOldModels: uniqueModels });
        } catch {
          // Non-critical; silently ignore
        }
      },

      executeReindex: async () => {
        try {
          const response = await fetch('/api/memory/reindex', { method: 'POST' });
          if (!response.ok) throw new Error('Reindex request failed');
          const data = await response.json();
          set({ orphanCount: 0, orphanOldModels: [] });
          return { migrated: data.migrated ?? 0, failed: data.failed ?? 0 };
        } catch {
          return { migrated: 0, failed: -1 };
        }
      },

      dismissOrphanWarning: () => {
        set({ orphanCount: 0, orphanOldModels: [] });
      },

      // ============ 重置 ============

      reset: () => {
        set(DEFAULT_CONFIG);
      },
    }),
);

export default useRetrievalStore;
