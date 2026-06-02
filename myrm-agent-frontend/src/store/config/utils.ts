import { SearchServiceConfig } from './types';

// 生成唯一ID
export const generateId = () => `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

// 生成配置名称
export const generateConfigName = (config: SearchServiceConfig) => {
  return config.search_service;
};
