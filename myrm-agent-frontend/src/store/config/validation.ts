import {
  validateSearchServiceConfig as validateSearchServiceConfigService,
  validateMCPConfig as validateMCPConfigService,
  type SearchServiceConfig,
  type ValidationResult,
} from '@/services/llm-config';

// 验证搜索服务配置
export const validateSearchServiceConfig = async (config: SearchServiceConfig): Promise<ValidationResult> => {
  return validateSearchServiceConfigService(config);
};

// 验证MCP服务配置
export const validateMCPConfig = validateMCPConfigService;
