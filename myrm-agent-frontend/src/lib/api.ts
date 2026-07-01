/**
 * [INPUT]
 * - @/lib/deploy-mode::getApiBaseUrl, getBackendBaseUrl (POS: 前端部署模式与基础地址解析层)
 *
 * [OUTPUT]
 * - API_BASE_URL: 规范化的 API 基础地址。
 * - BACKEND_BASE_URL: 规范化的后端基础地址。
 * - getApiUrl / getWsUrl / getStorageUrl: 统一 URL 拼接工具（getWsUrl 动态读取 getApiBaseUrl 以支持 sandbox 部署）。
 * - fetchWithTimeout / apiRequest: 前端统一请求入口（fetchWithTimeout 注入 mobile pair header；401/403 强登出拦截）
 *
 * [POS]
 * 前端 API 接入层。统一封装请求基址、超时、错误归一化、存储 URL 拼接以及安全拦截（全局强登出），避免脏配置污染请求链路。
 */
import { buildAuthLoginPath } from '@/lib/auth-redirect';
import { ensureLocalBackendReady } from '@/lib/backend-health';
import { getApiBaseUrl, getBackendBaseUrl, isLocalMode, shouldRedirectToLoginOnAuthFailure } from '@/lib/deploy-mode';
import { clearAuthToken } from '@/lib/guest';
import { withMobilePairHeaders } from '@/lib/mobileRemote';

const AUTH_LOGIN_PATH = buildAuthLoginPath();

function redirectToLoginAfterAuthFailure(): void {
  if (typeof window === 'undefined' || !shouldRedirectToLoginOnAuthFailure()) return;
  clearAuthToken();
  if (!window.location.pathname.startsWith(AUTH_LOGIN_PATH)) {
    window.location.href = AUTH_LOGIN_PATH;
  }
}

function createDynamicUrl(resolve: () => string): string {
  return {
    toString: () => resolve(),
    valueOf: () => resolve(),
  } as unknown as string;
}

export const API_BASE_URL = createDynamicUrl(getApiBaseUrl);

// 后端服务基础 URL（不含 API 路径前缀）
export const BACKEND_BASE_URL = createDynamicUrl(getBackendBaseUrl);

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
 * 将相对路径（如 /api/v1/storage/files/xxx）转换为完整的后端 URL
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
  // 相对路径直接拼接到后端基础 URL
  return `${BACKEND_BASE_URL}${url.startsWith('/') ? '' : '/'}${url}`;
};

/**
 * 错误严重程度
 */
export type ErrorSeverity = 'low' | 'medium' | 'high' | 'critical';

/**
 * API错误类
 */
export class ApiError extends Error {
  /** Structured detail payload from the backend 4xx/5xx response. */
  public data?: Record<string, unknown>;

  constructor(
    message: string,
    public code: number = 50001,
    public details: Array<{ field?: string; issue: string }> = [],
    public traceId?: string,
    public businessCode?: string,
    public severity?: ErrorSeverity,
    public retriable?: boolean,
    public retryAfter?: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * 根据HTTP状态码和BusinessCode推断错误严重程度
 * @param httpCode - HTTP状态码
 * @param businessCode - 业务错误码（可选，数字或字符串）
 * @returns ErrorSeverity
 */
function inferSeverity(httpCode: number, businessCode?: number | string): ErrorSeverity {
  // 优先根据BusinessCode精准判断
  if (businessCode !== undefined) {
    const code = Number(businessCode);

    // Critical: 认证和权限错误
    if (code === 40101 || code === 40301 || code === 53003) return 'critical';

    // High: 数据库错误、外部服务错误、AI错误
    if (code >= 51000 && code < 52000) return 'high'; // 所有数据库错误 (51xxx)
    if (code >= 52000 && code < 53000) return 'high'; // 外部服务错误 (52xxx)
    if (code === 53001 || code === 53002 || code === 53004) return 'high'; // AI错误
    if (code === 42901 || code === 50008) return 'high'; // 限流和超时

    // Medium: 客户端输入错误、资源错误
    if (code === 40001 || code === 40401 || code === 40901) return 'medium';

    // Low: 其他
    return 'low';
  }

  // 备选：根据HTTP状态码推断
  if (httpCode === 401 || httpCode === 403) return 'critical';
  if (httpCode >= 500) return 'high';
  if (httpCode === 429 || httpCode === 408) return 'high';
  if (httpCode >= 400) return 'medium';
  return 'low';
}

/**
 * 判断错误是否可重试
 * 基于HTTP状态码和BusinessCode判断
 * @param httpCode - HTTP状态码
 * @param businessCode - 业务错误码（可选，数字或字符串）
 * @returns boolean
 */
function inferRetriable(httpCode: number, businessCode?: number | string): boolean {
  // 优先根据BusinessCode精准判断
  if (businessCode !== undefined) {
    const code = Number(businessCode);

    // 明确可重试的BusinessCode
    if (code === 51005) return true; // DB_STORAGE_BUSY
    if (code === 51004) return true; // DB_TIMEOUT_ERROR
    if (code === 53002) return true; // AI_RATE_LIMIT_ERROR
    if (code === 53004) return true; // AI_TIMEOUT_ERROR
    if (code === 42901) return true; // RATE_LIMIT_ERROR
    if (code === 50008) return true; // TIMEOUT_ERROR
    if (code === 50003) return true; // SERVICE_UNAVAILABLE
    if (code === 52001) return true; // EXTERNAL_SERVICE_ERROR
    if (code === 52002) return true; // SEARCH_SERVICE_ERROR
    if (code === 52003) return true; // FILE_SERVICE_ERROR

    // 明确不可重试的BusinessCode
    if (code === 40101 || code === 40301) return false; // AUTH/PERMISSION错误
    if (code === 40401 || code === 40901) return false; // 资源不存在/冲突
    if (code === 40001) return false; // 验证错误
    if (code === 51003) return false; // DB_INTEGRITY_ERROR
    if (code === 53003) return false; // AI_AUTH_ERROR
  }

  // 备选：根据HTTP状态码推断
  if (httpCode === 408 || httpCode === 429) return true; // Timeout, Rate Limit
  if (httpCode === 502 || httpCode === 503 || httpCode === 504) return true; // Gateway errors
  if (httpCode === 500) return true; // Internal Server Error

  // 其他错误不可重试
  return false;
}

/**
 * 带超时控制的 fetch 函数。
 * 当调用者已传入 signal 时，通过 AbortSignal.any() 将取消信号与超时信号组合，
 * 两者任一触发即中止请求。传 timeout=0 可禁用超时（仅由 signal 控制）。
 */
export const fetchWithTimeout = async (
  endpoint: string,
  options: RequestInit = {},
  timeout: number = 30000,
): Promise<Response> => {
  const url = getApiUrl(endpoint);
  const callerSignal = options.signal;

  const signals: AbortSignal[] = [];
  if (callerSignal) signals.push(callerSignal);
  if (timeout > 0) signals.push(AbortSignal.timeout(timeout));

  const combinedSignal = signals.length > 0 ? AbortSignal.any(signals) : undefined;

  try {
    // 强制禁用 Next.js 缓存，防止在开发模式下缓存 502/ECONNREFUSED 错误
    // 默认携带 credentials 以确保 SSE 和普通请求都发送认证 cookie
    const incomingHeaders =
      options.headers instanceof Headers
        ? Object.fromEntries(options.headers.entries())
        : ((options.headers as Record<string, string> | undefined) ?? {});
    const headers = withMobilePairHeaders(incomingHeaders);
    const fetchOptions: RequestInit = {
      cache: 'no-store',
      credentials: 'include',
      ...options,
      headers,
      signal: combinedSignal,
    };
    const response = await fetch(url, fetchOptions);

    // 全局 401/403 强制登出拦截 (底层 Fetch 拦截)
    if (response.status === 401 || response.status === 403) {
      redirectToLoginAfterAuthFailure();
    }

    return response;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw error;
    }
    if (error instanceof Error && error.name === 'TimeoutError') {
      throw new ApiError(
        '请求超时，请检查网络连接或稍后重试',
        40408,
        [],
        undefined,
        'TIMEOUT_ERROR',
        'high',
        true, // 超时可重试
        3000, // 3秒后重试
      );
    }
    if (error instanceof Error && error.message.includes('Failed to fetch')) {
      throw new ApiError(
        '无法连接到服务器，请检查服务是否启动',
        50003,
        [],
        undefined,
        'NETWORK_ERROR',
        'high',
        true, // 网络错误可重试
        5000, // 5秒后重试
      );
    }
    throw error;
  }
};

/**
 * 获取认证 token
 */
const getAuthToken = (): string | null => {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('auth_token');
};

/**
 * 通用API请求函数
 * @param endpoint - API端点
 * @param options - 请求选项，支持 silent: true 禁用自动错误显示
 */
export const apiRequest = async <T = unknown>(
  endpoint: string,
  options: RequestInit & { silent?: boolean } = {},
): Promise<T> => {
  const { silent, ...fetchOptions } = options;

  // 保存请求上下文用于重试
  lastRequestContext = { endpoint, options: fetchOptions };

  try {
    if (typeof window !== 'undefined' && isLocalMode()) {
      await ensureLocalBackendReady();
    }

    // 获取认证 token
    const token = getAuthToken();

    // 如果是FormData，不设置Content-Type，让浏览器自动处理
    const headers: Record<string, string> = fetchOptions.body instanceof FormData
      ? { ...(fetchOptions.headers as Record<string, string>) }
      : { 'Content-Type': 'application/json', ...(fetchOptions.headers as Record<string, string>) };

    // 添加认证头
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetchWithTimeout(endpoint, {
      headers,
      ...fetchOptions,
    });

    if (!response.ok) {
      const errorText = await response.text();
      let errorMessage = errorText || `请求失败: ${response.status}`;
      let errorDetails = [];
      let traceId;
      let businessCode;
      let detailPayload: Record<string, unknown> | undefined;

      try {
        if (errorText) {
          const errorData = JSON.parse(errorText);
          const detail = errorData.detail;
          if (detail && typeof detail === 'object') {
            detailPayload = detail as Record<string, unknown>;
            errorMessage = detail.message || detail.error || errorMessage;
            if (detail.error && typeof detail.error === 'object') {
              errorDetails = detail.error.details || [];
              traceId = detail.error.trace_id;
            }
            businessCode = detail.code ?? errorData.code;
          } else {
            errorMessage = errorData.detail || errorData.message || errorData.error || errorMessage;
            if (errorData.error) {
              errorDetails = errorData.error.details || [];
              traceId = errorData.error.trace_id;
            }
            businessCode = errorData.code;
          }
        }
      } catch {
        // Ignore parse error, use raw text
      }

      // 拦截 Vault 锁定错误 (423)
      if (response.status === 423) {
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('vault-locked'));
        }
      }

      const apiError = new ApiError(
        errorMessage,
        response.status,
        errorDetails,
        traceId,
        businessCode ? String(businessCode) : undefined,
        inferSeverity(response.status, businessCode),
        inferRetriable(response.status, businessCode),
      );
      if (detailPayload) apiError.data = detailPayload;
      throw apiError;
    }

    // 处理空响应（204 No Content 或无 JSON body）
    const contentLength = response.headers.get('content-length');
    const contentType = response.headers.get('content-type') || '';
    if (response.status === 204 || contentLength === '0' || !contentType.includes('application/json')) {
      return {} as T;
    }

    const responseData = await response.json();

    // 直接使用新的标准响应格式
    if (responseData.success === false) {
      const businessCode = responseData.code || 50001;
      const httpStatus = response.status;

      // 全局 401/403 强制登出拦截 (针对业务错误码)
      if (businessCode === 40101 || businessCode === 40301) {
        redirectToLoginAfterAuthFailure();
      }

      throw new ApiError(
        responseData.message || '请求失败',
        httpStatus, // HTTP状态码
        responseData.error?.details || [],
        responseData.error?.trace_id,
        String(businessCode), // businessCode转为字符串存储
        inferSeverity(httpStatus, businessCode), // 传入businessCode进行精准判断
        inferRetriable(httpStatus, businessCode), // 传入businessCode进行精准判断
        responseData.error?.retry_after,
      );
    }

    return responseData.data || responseData;
  } catch (error) {
    // 全局错误拦截和显示
    if (!silent && error instanceof ApiError) {
      showApiError(error);
    }
    throw error;
  }
};

/**
 * 存储最后一次请求的上下文，用于重试
 */
let lastRequestContext: {
  endpoint: string;
  options: RequestInit;
} | null = null;

/**
 * 重试最后一次请求
 */
export const retryLastRequest = async (): Promise<unknown> => {
  if (lastRequestContext) {
    return apiRequest(lastRequestContext.endpoint, lastRequestContext.options);
  }
  return Promise.reject(new Error('没有可重试的请求'));
};

/**
 * 显示API错误提示
 * @param error - 错误对象
 * @param duration - 显示时长（毫秒），默认根据severity自动判断
 */
export const showApiError = (error: unknown, duration?: number): void => {
  // 动态导入
  import('@/hooks/useToast').then(({ toast }) => {
    import('./utils/errorManager').then(({ errorManager }) => {
      if (error instanceof ApiError) {
        // 去重检查
        if (!errorManager.shouldShow(error)) {
          return; // 跳过重复错误
        }

        const message = error.message;
        let description = message;

        // 添加详情
        if (error.details.length > 0) {
          const details = error.details
            .map((detail) => (detail.field ? `${detail.field}: ${detail.issue}` : detail.issue))
            .join('; ');
          description = `${message}\n详情: ${details}`;
        }

        // 添加trace ID
        if (error.traceId) {
          description += `\n追踪ID: ${error.traceId}`;
        }

        // 根据severity决定显示方式和时长
        const severity = error.severity || 'medium';
        let finalDuration = duration;

        if (!finalDuration) {
          switch (severity) {
            case 'critical':
              finalDuration = Infinity; // 永久显示
              break;
            case 'high':
              finalDuration = 10000; // 10秒
              break;
            case 'medium':
              finalDuration = 5000; // 5秒
              break;
            case 'low':
              return; // 低优先级错误不显示
          }
        }

        // 根据severity选择toast类型和选项
        const toastAction = error.retriable
          ? {
              label: '重试',
              onClick: () => {
                retryLastRequest().catch((retryError) => {
                  console.warn('重试失败:', retryError);
                });
              },
            }
          : undefined;

        // 根据severity选择不同的toast类型
        if (severity === 'critical' || severity === 'high') {
          // Critical和High用error（红色）
          toast.error(description, {
            duration: finalDuration,
            action: toastAction,
          });
        } else if (severity === 'medium') {
          // Medium用warning（黄色）
          toast.warning(description, {
            duration: finalDuration,
            action: toastAction,
          });
        }
        // Low不显示（已在前面return）
      } else if (error instanceof Error) {
        // 非ApiError，使用默认显示
        toast({
          title: '错误',
          description: error.message,
          duration: duration || 5000,
          variant: 'destructive',
        });
      } else {
        // 未知错误
        toast({
          title: '错误',
          description: '未知错误',
          duration: duration || 5000,
          variant: 'destructive',
        });
      }
    });
  });
};
