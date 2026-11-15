/**
 * [INPUT]
 * - @/lib/deploy-mode::getApiBaseUrl (POS: 前端部署模式与基础地址解析层)
 * - @/lib/utils/backend-url::BACKEND_BASE_URL, createDynamicUrl (POS: 后端服务基础地址层)
 * - @/lib/mediaReference::parseMediaReference (POS: `media://<id>` 媒体库引用的读写)
 *
 * [OUTPUT]
 * - API_BASE_URL: 规范化的 API 基础地址。
 * - BACKEND_BASE_URL: 规范化的后端基础地址。
 * - getApiUrl / getWebuiUrl / getWsUrl / getStorageUrl: 统一 URL 拼接工具（getWsUrl 动态读取 getApiBaseUrl 以支持 sandbox 部署；
 *   getStorageUrl 把 `vault://`、`media://` 引用解析成可直接给 img/video/audio 使用的后端地址）。
 *
 * [POS]
 * 前端 URL 拼接层。只做地址计算，不发请求，不拖入 API 请求模块的错误处理与 toast 依赖；`@/lib/api` 重新导出本模块的全部符号。
 */
import { getApiBaseUrl } from '@/lib/deploy-mode';
import { parseMediaReference } from '@/lib/mediaReference';
import { BACKEND_BASE_URL, createDynamicUrl } from '@/lib/utils/backend-url';

export const API_BASE_URL = createDynamicUrl(getApiBaseUrl);

export { BACKEND_BASE_URL };

/**
 * 获取完整的API地址
 */
export const getApiUrl = (endpoint: string): string => {
  if (endpoint.startsWith('/webui')) {
    return getWebuiUrl(endpoint);
  }
  return `${API_BASE_URL}${endpoint}`;
};

/**
 * WebUI 路由挂载在后端 `/webui`（非 `/api/v1`）。
 * 本地开发经 Next rewrites 代理；沙箱/远程使用 BACKEND_BASE_URL。
 */
export const getWebuiUrl = (endpoint: string): string => {
  const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  const webuiPath = path.startsWith('/webui') ? path : `/webui${path}`;
  if (BACKEND_BASE_URL) {
    return `${BACKEND_BASE_URL}${webuiPath}`;
  }
  return webuiPath;
};

/**
 * 获取 WebSocket URL（将 http(s) 转换为 ws(s)）
 */
export const getWsUrl = (endpoint: string): string => {
  const base = getApiBaseUrl().replace(/^http/, 'ws');
  return `${base}${endpoint}`;
};

/**
 * 获取存储服务的完整 URL
 * 将相对路径（如 /api/v1/storage/files/xxx）、`vault://` 与 `media://` 引用转换为完整的后端 URL
 */
export const getStorageUrl = (url: string): string => {
  // 空 URL 直接返回，让调用者处理
  if (!url) {
    return '';
  }
  // 如果已经是完整 URL，直接返回
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url;
  }
  if (url.startsWith('vault://')) {
    const vaultId = url.slice('vault://'.length).split(':')[0];
    return `${BACKEND_BASE_URL}/api/v1/files/vault/${vaultId}/content`;
  }
  const mediaId = parseMediaReference(url);
  if (mediaId) {
    return getApiUrl(`/media/${encodeURIComponent(mediaId)}/file`);
  }
  // 相对路径直接拼接到后端基础 URL
  return `${BACKEND_BASE_URL}${url.startsWith('/') ? '' : '/'}${url}`;
};
