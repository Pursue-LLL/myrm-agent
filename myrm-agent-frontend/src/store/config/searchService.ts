import { translateI18nKey } from '@/services/i18nToastService';
import { toast } from '@/lib/utils/toast';
import { SearchServiceConfigItem, SearchServiceConfig } from './types';
import { runWebSearchConfigGapAction, resolveWebSearchConfigGapActionLabel } from './webSearchConfigGap';

export {
  SEARCH_SETTINGS_PATH,
  resolveWebSearchConfigGapActionLabel,
  resolveWebSearchConfigGapActionLabelKey,
  runWebSearchConfigGapAction,
} from './webSearchConfigGap';

const MAX_CHAIN_SIZE = 5;

type LegacySearchConfigItem = SearchServiceConfigItem & { role?: 'primary' | 'fallback' };

/**
 * Migrate legacy role primary/fallback → priority integers (mirrors server migration).
 */
export const migrateSearchConfigItem = (config: LegacySearchConfigItem): SearchServiceConfigItem => {
  if (typeof config.priority === 'number' && config.priority >= 1 && config.priority <= MAX_CHAIN_SIZE) {
    const { role: _role, ...rest } = config;
    return rest;
  }
  const role = config.role ?? 'primary';
  const { role: _role, ...rest } = config;
  return {
    ...rest,
    priority: role === 'fallback' ? 2 : 1,
  };
};

export const normalizeSearchServiceConfigs = (configs: LegacySearchConfigItem[]): SearchServiceConfigItem[] => {
  const migrated = configs.map(migrateSearchConfigItem);
  const used = new Set<number>();
  let next = 1;
  return migrated.map((config) => {
    let priority = config.priority;
    if (!Number.isInteger(priority) || priority < 1 || priority > MAX_CHAIN_SIZE || used.has(priority)) {
      while (next <= MAX_CHAIN_SIZE && used.has(next)) {
        next += 1;
      }
      priority = next <= MAX_CHAIN_SIZE ? next : MAX_CHAIN_SIZE;
    }
    used.add(priority);
    next = Math.max(next, priority + 1);
    return { ...config, priority };
  });
};

// 生成唯一的搜索服务配置 ID
export const generateSearchServiceConfigId = (): string => {
  return `search-service-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
};

// 获取搜索服务的显示名称（manifest 未加载时的后备）
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
    brave: 'Brave Search',
    serper: 'Serper',
    volcengine_doubao: 'Volcengine Doubao',
  };
  return displayNames[serviceType] || serviceType;
};

const ensurePriority = (config: SearchServiceConfigItem): SearchServiceConfigItem => {
  const priority =
    typeof config.priority === 'number' && config.priority >= 1 && config.priority <= MAX_CHAIN_SIZE
      ? config.priority
      : 1;
  return { ...config, priority };
};

const disableSamePriority = (
  configs: SearchServiceConfigItem[],
  priority: number,
  exceptId?: string,
): SearchServiceConfigItem[] => {
  return configs.map((c) => (c.id !== exceptId && c.enabled && c.priority === priority ? { ...c, enabled: false } : c));
};

// 加载搜索服务配置列表（已废弃，persist 自动处理）
export const loadSearchServiceConfigs = (): SearchServiceConfigItem[] => {
  return [];
};

export const setSearchServiceConfigs = (configs: LegacySearchConfigItem[]): SearchServiceConfigItem[] => {
  return normalizeSearchServiceConfigs(configs);
};

export const addSearchServiceConfig = (
  currentConfigs: SearchServiceConfigItem[],
  config: SearchServiceConfigItem,
): SearchServiceConfigItem[] => {
  const validatedConfig = ensurePriority(config);
  if (validatedConfig.enabled) {
    const withoutConflict = disableSamePriority(currentConfigs, validatedConfig.priority);
    return [...withoutConflict, validatedConfig];
  }
  return [...currentConfigs, validatedConfig];
};

export const updateSearchServiceConfig = (
  currentConfigs: SearchServiceConfigItem[],
  id: string,
  updates: Partial<SearchServiceConfigItem>,
): SearchServiceConfigItem[] => {
  const targetConfig = currentConfigs.find((c) => c.id === id);
  if (!targetConfig) {
    return currentConfigs;
  }

  const merged = ensurePriority({ ...targetConfig, ...updates });
  const willEnable = updates.enabled === true || (updates.enabled === undefined && merged.enabled);

  if (willEnable) {
    const withoutConflict = disableSamePriority(currentConfigs, merged.priority, id);
    return withoutConflict.map((config) => (config.id === id ? merged : config));
  }

  return currentConfigs.map((config) =>
    config.id === id ? { ...config, ...updates, priority: merged.priority } : config,
  );
};

export const removeSearchServiceConfig = (
  currentConfigs: SearchServiceConfigItem[],
  id: string,
): SearchServiceConfigItem[] => {
  return currentConfigs.filter((config) => config.id !== id);
};

export const enableSearchServiceConfig = (
  currentConfigs: SearchServiceConfigItem[],
  id: string,
): SearchServiceConfigItem[] => {
  const targetConfig = currentConfigs.find((c) => c.id === id);
  if (!targetConfig) {
    return currentConfigs;
  }

  const withoutConflict = disableSamePriority(currentConfigs, targetConfig.priority, id);
  return withoutConflict.map((config) => ({
    ...config,
    enabled: config.id === id ? true : config.enabled,
  }));
};

export const suggestNextPriority = (configs: SearchServiceConfigItem[]): number => {
  const enabled = configs.filter((c) => c.enabled);
  const used = new Set(enabled.map((c) => c.priority));
  for (let p = 1; p <= MAX_CHAIN_SIZE; p += 1) {
    if (!used.has(p)) {
      return p;
    }
  }
  return MAX_CHAIN_SIZE;
};

/**
 * Returns head of enabled priority chain for readiness checks (server builds full chain).
 */
export const getActiveSearchServiceConfig = (configs: SearchServiceConfigItem[]): SearchServiceConfig | null => {
  const enabled = configs
    .filter((c) => c.enabled)
    .sort((a, b) => a.priority - b.priority)
    .slice(0, MAX_CHAIN_SIZE);

  if (enabled.length === 0) {
    return null;
  }

  const head = enabled[0];
  return {
    search_service: head.search_service,
    api_key: head.api_key || null,
    api_base: head.api_base || null,
    extra_params: head.extra_params || null,
  };
};

export const showSearchNotConfiguredToast = (): void => {
  const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
  const isZh = lang?.startsWith('zh');
  const title = translateI18nKey(
    'chat.searchNotConfigured.title',
    isZh ? '搜索服务未配置' : 'Search Service Not Configured',
  );
  const description = translateI18nKey(
    'chat.searchNotConfigured.description',
    isZh
      ? '此模式需要搜索服务，请先在设置中添加并启用搜索服务。'
      : 'This mode requires a search service. Please add and enable one in Settings first.',
  );
  toast.warning(title, {
    description,
    duration: 6000,
    action: {
      label: resolveWebSearchConfigGapActionLabel(isZh),
      onClick: () => {
        void runWebSearchConfigGapAction();
      },
    },
  });
};

export const guardSearchServiceConfigured = (configs: SearchServiceConfigItem[]): boolean => {
  if (getActiveSearchServiceConfig(configs)) {
    return true;
  }
  showSearchNotConfiguredToast();
  return false;
};
