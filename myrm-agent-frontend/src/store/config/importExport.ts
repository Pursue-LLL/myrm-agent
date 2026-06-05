import { gateMcpConfigBatch } from '@/hooks/useMcpSecurityGate';

import { ConfigState, SearchServiceConfigItem, MCPServiceConfig } from './types';
import { ProviderConfig, DefaultModelConfig, CustomModelInfo } from './providerTypes';
import { migrateProvidersBundle } from './providerIdentityMigration';

// 完整配置导出接口
export interface FullExportConfig {
  // ConfigStore 配置
  systemInstructions?: string;
  fetchRawWebpage?: boolean;
  extractDocumentText?: boolean;
  generateSearchSuggestions?: boolean;
  enableCostEstimation?: boolean;
  searchServiceConfigs?: SearchServiceConfigItem[];
  mcpConfigs?: MCPServiceConfig[];

  // ProviderStore 配置
  providers?: ProviderConfig[];
  defaultModelConfig?: DefaultModelConfig;
  customModelInfo?: Record<string, CustomModelInfo>;
}

// 导出配置
export const exportConfig = (
  configState: Partial<ConfigState>,
  providerState?: {
    providers?: ProviderConfig[];
    defaultModelConfig?: DefaultModelConfig;
    customModelInfo?: Record<string, CustomModelInfo>;
  },
) => {
  const exportData = {
    version: '4.0.0', // 升级版本号，新的多配置格式
    timestamp: new Date().toISOString(),
    config: {
      // ConfigStore 配置
      systemInstructions: configState.systemInstructions,
      fetchRawWebpage: configState.fetchRawWebpage,
      extractDocumentText: configState.extractDocumentText,
      generateSearchSuggestions: configState.generateSearchSuggestions,
      enableCostEstimation: configState.enableCostEstimation,
      searchServiceConfigs: configState.searchServiceConfigs,
      mcpConfigs: configState.mcpConfigs,

      // ProviderStore 配置
      providers: providerState?.providers,
      defaultModelConfig: providerState?.defaultModelConfig,
      customModelInfo: providerState?.customModelInfo,
    },
  };

  return JSON.stringify(exportData, null, 2);
};

// 导入配置
export const importConfig = async (
  configJson: string,
  setters: {
    // ConfigStore setters
    setSystemInstructions?: (instructions: string) => void;
    setFetchRawWebpage?: (fetch: boolean) => void;
    setExtractDocumentText?: (enabled: boolean) => void;
    setGenerateSearchSuggestions?: (generate: boolean) => void;
    setEnableCostEstimation?: (enable: boolean) => void;
    setSearchServiceConfigs?: (configs: SearchServiceConfigItem[]) => void;
    setMCPConfigs?: (configs: MCPServiceConfig[]) => void;
    // ProviderStore setters
    setProviders?: (providers: ProviderConfig[]) => void;
    setDefaultModelConfig?: (config: DefaultModelConfig) => void;
    setCustomModelInfo?: (info: Record<string, CustomModelInfo>) => void;
  },
): Promise<{ success: boolean; messageKey: string }> => {
  try {
    const importData = JSON.parse(configJson);

    if (!importData.config) {
      return { success: false, messageKey: 'invalidFormat' };
    }

    const config = importData.config;

    // ConfigStore 配置
    if (config.systemInstructions !== undefined && setters.setSystemInstructions) {
      setters.setSystemInstructions(config.systemInstructions);
    }

    if (config.fetchRawWebpage !== undefined && setters.setFetchRawWebpage) {
      setters.setFetchRawWebpage(config.fetchRawWebpage);
    }

    if (config.extractDocumentText !== undefined && setters.setExtractDocumentText) {
      setters.setExtractDocumentText(config.extractDocumentText);
    }

    if (config.generateSearchSuggestions !== undefined && setters.setGenerateSearchSuggestions) {
      setters.setGenerateSearchSuggestions(config.generateSearchSuggestions);
    }

    if (config.enableCostEstimation !== undefined && setters.setEnableCostEstimation) {
      setters.setEnableCostEstimation(config.enableCostEstimation);
    }

    // 新格式：searchServiceConfigs 数组
    if (config.searchServiceConfigs && Array.isArray(config.searchServiceConfigs) && setters.setSearchServiceConfigs) {
      setters.setSearchServiceConfigs(config.searchServiceConfigs);
    }

    if (config.mcpConfigs && Array.isArray(config.mcpConfigs) && setters.setMCPConfigs) {
      const mcpList = config.mcpConfigs as MCPServiceConfig[];
      const batchGate = await gateMcpConfigBatch(mcpList);
      if (batchGate.blocked) {
        return { success: false, messageKey: 'mcpImportSecurityBlocked' };
      }
      if (batchGate.needsAcknowledgement) {
        return { success: false, messageKey: 'mcpImportSecurityAckRequired' };
      }
      setters.setMCPConfigs(config.mcpConfigs);
    }

    const migratedProviders =
      config.providers || config.defaultModelConfig || config.customModelInfo
        ? migrateProvidersBundle({
            providers: config.providers ?? [],
            defaultModelConfig: config.defaultModelConfig,
            customModelInfo: config.customModelInfo ?? {},
          })
        : null;

    // ProviderStore 配置
    if (migratedProviders && Array.isArray(migratedProviders.providers) && setters.setProviders) {
      setters.setProviders(migratedProviders.providers);
    }

    if (migratedProviders?.defaultModelConfig && setters.setDefaultModelConfig) {
      setters.setDefaultModelConfig(migratedProviders.defaultModelConfig);
    }

    if (migratedProviders?.customModelInfo && setters.setCustomModelInfo) {
      setters.setCustomModelInfo(migratedProviders.customModelInfo);
    }

    return { success: true, messageKey: 'importSuccess' };
  } catch (error) {
    console.error('Import config failed:', error);
    return {
      success: false,
      messageKey: 'parseError',
    };
  }
};
