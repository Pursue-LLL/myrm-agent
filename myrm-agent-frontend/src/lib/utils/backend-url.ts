/**
 * [INPUT]
 * @/lib/deploy-mode::getBackendBaseUrl (POS: 前端部署模式与基础地址解析层)
 *
 * [OUTPUT]
 * BACKEND_BASE_URL: 规范化的后端服务基础地址（动态解析，不含 API 路径前缀）
 * createDynamicUrl: 动态 URL 构建器（懒解析 toString/valueOf 伪装 string）
 *
 * [POS]
 * 后端服务基础地址层。独立于 API 请求层，供 URL 类工具与 API 层共同消费，
 * 避免轻量 URL 工具反向拖入重量级 API 请求模块。
 */
import { getBackendBaseUrl } from '@/lib/deploy-mode';

function createDynamicUrl(resolve: () => string): string {
  return {
    toString: () => resolve(),
    valueOf: () => resolve(),
  } as unknown as string;
}

export { createDynamicUrl };

// 后端服务基础 URL（不含 API 路径前缀）
export const BACKEND_BASE_URL = createDynamicUrl(getBackendBaseUrl);
