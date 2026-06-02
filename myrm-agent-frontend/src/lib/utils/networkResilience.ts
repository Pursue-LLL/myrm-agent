/**
 * [INPUT]
 * (None)
 *
 * [OUTPUT]
 * isRetryableHttpStatus: Determines if an HTTP status code indicates a transient, retryable error.
 * isRetryableWebSocketClose: Determines if a WebSocket close code is retryable.
 * FatalNetworkError: Custom error class for non-retryable network failures.
 * isArchiveRestoreActionInvalidError: Identifies typed archive restore validation failures.
 *
 * [POS]
 * Unified Network Resilience Policy Layer. Centralizes retry and fail-fast logic for
 * both HTTP SSE streams and WebSockets to prevent retry storms and ensure graceful degradation.
 */

/**
 * 判定 HTTP 状态码是否为瞬态可重试异常。
 *
 * 白名单：
 * - 408 Request Timeout
 * - 429 Too Many Requests (需结合 Retry-After，但通常可退避重试)
 * - 502 Bad Gateway (代理或服务热重启)
 * - 503 Service Unavailable
 * - 504 Gateway Timeout
 */
export function isRetryableHttpStatus(status: number): boolean {
  return [408, 429, 502, 503, 504].includes(status);
}

/**
 * 判定 WebSocket 关闭码是否为可重试异常。
 * 参考 RFC 6455 规范。
 *
 * 明确拒绝重试的黑名单：
 * - 1000 Normal Closure (正常关闭不重试，除非业务要求)
 * - 1003 Unsupported Data
 * - 1007 Invalid Frame Payload Data
 * - 1008 Policy Violation (如鉴权失败、权限被褫夺，绝对不可重试)
 * - 1009 Message Too Big
 * - 1010 Mandatory Ext
 * - 1011 Internal Server Error (虽然是服务端异常，但通常代表服务端代码崩溃，盲目重试易加雪崩，视业务而定。这里我们为了 Fail-Fast，将其视为不可重试，或者给其有限次数)
 *
 * 我们采用白名单放行（仅以下状态重试）：
 * - 1001 Going Away (服务端关闭/重启)
 * - 1006 Abnormal Closure (断网)
 * - 1012 Service Restart
 * - 1013 Try Again Later
 * - 1014 Bad Gateway
 */
export function isRetryableWebSocketClose(code: number): boolean {
  return [1001, 1006, 1012, 1013, 1014].includes(code);
}

export const ARCHIVE_RESTORE_ACTION_INVALID = 'archive_restore_action_invalid';

interface FatalNetworkErrorOptions {
  status?: number;
  errorCode?: string;
  detail?: string;
  responseBody?: string;
}

/**
 * 致命网络错误。
 * 用于在重试循环中抛出以实现快速失败（Fail-Fast）。
 */
export class FatalNetworkError extends Error {
  public status?: number;
  public errorCode?: string;
  public detail?: string;
  public responseBody?: string;

  constructor(message: string, statusOrOptions?: number | FatalNetworkErrorOptions) {
    super(message);
    this.name = 'FatalNetworkError';
    if (typeof statusOrOptions === 'number') {
      this.status = statusOrOptions;
      return;
    }
    this.status = statusOrOptions?.status;
    this.errorCode = statusOrOptions?.errorCode;
    this.detail = statusOrOptions?.detail;
    this.responseBody = statusOrOptions?.responseBody;
  }
}

export function isArchiveRestoreActionInvalidError(error: unknown): error is FatalNetworkError {
  return error instanceof FatalNetworkError && error.errorCode === ARCHIVE_RESTORE_ACTION_INVALID;
}
