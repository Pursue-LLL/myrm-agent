import { BACKEND_BASE_URL } from '@/lib/api';

/**
 * 获取后端服务基础 URL（不含 API 路径前缀）
 * @returns 后端服务基础 URL
 */
export const getBackendUrl = (): string => {
  return BACKEND_BASE_URL;
};
