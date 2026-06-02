import { showI18nToast } from '@/services/i18nToastService';
import { isLocalMode } from '@/lib/deploy-mode';
import useConfigStore from '@/store/useConfigStore';
import { probeAndBuildQuickSearchConfig } from '@/store/config/quickSearchSetup';
import { SearchServiceConfigItem, SearchServiceConfig } from './types';

/**
 * 搜索服务配置管理模块
 *
 * 注意：不再手动管理 localStorage
 * 所有持久化由 useConfigStore 的 persist 中间件自动处理
 */

// 生成唯一的搜索服务配置 ID
export const generateSearchServiceConfigId = (): string => {
  return `search-service-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
};

// 获取搜索服务的显示名称
export const getSearchServiceDisplayName = (serviceType: string): string => {
  const displayNames: Record<string, string> = {
    perplexity: 'Perplexity',
    tavily: 'Tavily',
    exa_ai: 'Exa AI',
    parallel_ai: 'Parallel AI',
    google_pse: 'Google PSE',
    dataforseo: 'DataForSEO',
    firecrawl: 'Firecrawl',
    searxng: 'SearXNG',
  };
  return displayNames[serviceType] || serviceType;
};

/**
 * Ensure config has a valid role field (defaults to 'primary')
 */
const ensureRole = (config: SearchServiceConfigItem): SearchServiceConfigItem => {
  return {
    ...config,
    role: config.role || 'primary',
  };
};

// 加载搜索服务配置列表（已废弃，persist 自动处理）
// 保留此函数仅为了兼容性，实际上 persist 会自动加载
export const loadSearchServiceConfigs = (): SearchServiceConfigItem[] => {
  // persist 中间件会自动加载，这里返回空数组作为初始值
  return [];
};

// 设置所有搜索服务配置
export const setSearchServiceConfigs = (configs: SearchServiceConfigItem[]): SearchServiceConfigItem[] => {
  return configs.map(ensureRole);
};

// 添加搜索服务配置
export const addSearchServiceConfig = (
  currentConfigs: SearchServiceConfigItem[],
  config: SearchServiceConfigItem,
): SearchServiceConfigItem[] => {
  const validatedConfig = ensureRole(config);

  if (validatedConfig.enabled) {
    const newConfigs = currentConfigs.map((c) => ({
      ...c,
      enabled: c.role === validatedConfig.role ? false : c.enabled,
    }));
    newConfigs.push(validatedConfig);
    return newConfigs;
  }
  return [...currentConfigs, validatedConfig];
};

// 更新搜索服务配置
export const updateSearchServiceConfig = (
  currentConfigs: SearchServiceConfigItem[],
  id: string,
  updates: Partial<SearchServiceConfigItem>,
): SearchServiceConfigItem[] => {
  const targetConfig = currentConfigs.find((c) => c.id === id);
  if (!targetConfig) {
    return currentConfigs;
  }

  const validatedUpdates = updates.role ? { ...updates, role: updates.role || 'primary' } : updates;
  const updatedConfig = ensureRole({ ...targetConfig, ...validatedUpdates });

  if (validatedUpdates.enabled === true) {
    return currentConfigs.map((config) => ({
      ...config,
      ...(config.id === id ? validatedUpdates : {}),
      enabled: config.id === id ? true : config.role === updatedConfig.role ? false : config.enabled,
    }));
  }

  return currentConfigs.map((config) => (config.id === id ? { ...config, ...validatedUpdates } : config));
};

// 删除搜索服务配置
export const removeSearchServiceConfig = (
  currentConfigs: SearchServiceConfigItem[],
  id: string,
): SearchServiceConfigItem[] => {
  return currentConfigs.filter((config) => config.id !== id);
};

// 启用指定的搜索服务配置（禁用同角色的其他配置）
export const enableSearchServiceConfig = (
  currentConfigs: SearchServiceConfigItem[],
  id: string,
): SearchServiceConfigItem[] => {
  const targetConfig = currentConfigs.find((c) => c.id === id);
  if (!targetConfig) {
    return currentConfigs;
  }

  return currentConfigs.map((config) => ({
    ...config,
    enabled: config.id === id ? true : config.role === targetConfig.role ? false : config.enabled,
  }));
};

/**
 * Get active search service configuration (primary + fallback)
 * Returns the primary service with optional fallback_config
 */
export const getActiveSearchServiceConfig = (configs: SearchServiceConfigItem[]): SearchServiceConfig | null => {
  const enabledConfigs = configs.filter((c) => c.enabled);

  const primaryConfig = enabledConfigs.find((c) => c.role === 'primary');
  const fallbackConfig = enabledConfigs.find((c) => c.role === 'fallback');

  if (!primaryConfig) {
    return null;
  }

  // Build primary service config
  const result: SearchServiceConfig = {
    search_service: primaryConfig.search_service,
    api_key: primaryConfig.api_key || null,
    api_base: primaryConfig.api_base || null,
    extra_params: primaryConfig.extra_params || null,
  };

  // Attach fallback if exists
  if (fallbackConfig) {
    result.fallback_config = {
      search_service: fallbackConfig.search_service,
      api_key: fallbackConfig.api_key || null,
      api_base: fallbackConfig.api_base || null,
      extra_params: fallbackConfig.extra_params || null,
    };
  }

  return result;
};

/**
 * Show a warning toast when search service is not configured.
 * Centralized here to avoid duplicating toast parameters across components.
 */
export const showSearchNotConfiguredToast = (): void => {
  const local = isLocalMode();
  showI18nToast('chat.searchNotConfigured.title', undefined, {
    descriptionKey: 'chat.searchNotConfigured.description',
    type: 'warning',
    duration: 6000,
    action: {
      label: local ? 'chat.searchNotConfigured.enableAction' : 'chat.searchNotConfigured.action',
      onClick: () => {
        void (async () => {
          if (local) {
            const config = await probeAndBuildQuickSearchConfig();
            if (config) {
              useConfigStore.getState().addSearchServiceConfig(config);
              return;
            }
          }
          window.location.href = '/settings/search';
        })();
      },
    },
  });
};

/**
 * Check if search service is configured and show toast if not.
 * Returns true if search is available, false otherwise.
 */
export const guardSearchServiceConfigured = (configs: SearchServiceConfigItem[]): boolean => {
  if (getActiveSearchServiceConfig(configs)) return true;
  showSearchNotConfiguredToast();
  return false;
};
