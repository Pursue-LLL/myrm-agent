import { MCPServiceConfig } from './types';
import { normalizeMCPServiceConfig, normalizeMCPServiceConfigs } from '@/lib/utils/mcpConfigNormalizer';

/**
 * MCP 配置管理模块
 *
 * 注意：不再手动管理 localStorage
 * 所有持久化由 useConfigStore 的 persist 中间件自动处理
 */

// 设置所有MCP配置
export const setMCPConfigs = (configs: MCPServiceConfig[]) => {
  return normalizeMCPServiceConfigs(configs);
};

// 添加MCP配置
export const addMCPConfig = (currentConfigs: MCPServiceConfig[], config: MCPServiceConfig): MCPServiceConfig[] => {
  return [...normalizeMCPServiceConfigs(currentConfigs), normalizeMCPServiceConfig(config)];
};

// 更新MCP配置
export const updateMCPConfig = (
  currentConfigs: MCPServiceConfig[],
  index: number,
  config: MCPServiceConfig,
): MCPServiceConfig[] => {
  const newConfigs = [...normalizeMCPServiceConfigs(currentConfigs)];
  newConfigs[index] = normalizeMCPServiceConfig(config);
  return newConfigs;
};

// 删除MCP配置
export const removeMCPConfig = (currentConfigs: MCPServiceConfig[], index: number): MCPServiceConfig[] => {
  return currentConfigs.filter((_, i) => i !== index);
};

// 切换MCP配置启用状态
export const toggleMCPConfig = (currentConfigs: MCPServiceConfig[], index: number): MCPServiceConfig[] => {
  const newConfigs = [...normalizeMCPServiceConfigs(currentConfigs)];
  newConfigs[index] = normalizeMCPServiceConfig({ ...newConfigs[index], enabled: !newConfigs[index].enabled });
  return newConfigs;
};

// 加载MCP配置（已废弃，persist 自动处理）
// 保留此函数仅为了兼容性，实际上 persist 会自动加载
export const loadMCPConfigs = (): MCPServiceConfig[] => {
  // persist 中间件会自动加载，这里返回空数组作为初始值
  return [];
};
