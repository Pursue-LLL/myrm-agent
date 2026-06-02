/**
 * [INPUT]
 * - window.__TAURI__ (POS: Tauri 运行时桥接)
 * - process.env.NEXT_PUBLIC_API_URL (POS: 桌面端后端地址配置)
 *
 * [OUTPUT]
 * - isTauriEnvironment: 判断是否运行在 Tauri 环境。
 * - invokeTauriCommand / listenTauriEvent / emitTauriEvent: Tauri 原生桥接。
 * - getBackendBaseUrl: 返回安全的桌面端后端地址。
 *
 * [POS]
 * Tauri 原生桥接层。负责桌面端命令调用和后端地址解析，避免无效配置污染桌面请求。
 */
/**
 * Tauri 环境检测和 API 封装
 *
 * 提供统一的接口来检测是否在 Tauri 环境中运行，
 * 以及调用 Tauri 的原生 API。
 */

// Tauri API 类型定义
interface TauriWindow {
  __TAURI__?: {
    invoke: <T>(cmd: string, args?: Record<string, unknown>) => Promise<T>;
    event: {
      listen: (event: string, handler: (event: unknown) => void) => Promise<() => void>;
      emit: (event: string, payload?: unknown) => Promise<void>;
    };
  };
}

const DEFAULT_TAURI_BACKEND_BASE_URL = 'http://localhost:8080';
const INVALID_BASE_URL_VALUES = new Set(['undefined', 'null']);

function normalizeConfiguredBaseUrl(value: string | null | undefined, fallback: string): string {
  const candidate = value?.trim();
  if (!candidate) return fallback;
  if (INVALID_BASE_URL_VALUES.has(candidate.toLowerCase())) return fallback;

  try {
    const parsed = new URL(candidate);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return fallback;
    }
  } catch {
    return fallback;
  }

  return candidate.replace(/\/+$/, '');
}

declare global {
  interface Window extends TauriWindow {}
}

/**
 * 检测是否在 Tauri 环境中运行
 */
export function isTauriEnvironment(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  return window.__TAURI__ !== undefined;
}

/**
 * 调用 Tauri 命令
 */
export async function invokeTauriCommand<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  if (!isTauriEnvironment()) {
    throw new Error('Not running in Tauri environment');
  }

  try {
    return await window.__TAURI__!.invoke<T>(command, args);
  } catch (error) {
    console.error(`Failed to invoke Tauri command: ${command}`, error);
    throw error;
  }
}

/**
 * Tauri 后端管理 API
 */
export const tauriBackend = {
  /**
   * 启动 Python 后端
   */
  async start(): Promise<string> {
    return invokeTauriCommand<string>('start_backend');
  },

  /**
   * 停止 Python 后端
   */
  async stop(): Promise<string> {
    return invokeTauriCommand<string>('stop_backend');
  },

  /**
   * 检查后端健康状态
   */
  async checkHealth(): Promise<boolean> {
    return invokeTauriCommand<boolean>('check_backend_health');
  },
};

/**
 * 监听 Tauri 事件
 */
export async function listenTauriEvent(event: string, handler: (payload: unknown) => void): Promise<() => void> {
  if (!isTauriEnvironment()) {
    throw new Error('Not running in Tauri environment');
  }

  return await window.__TAURI__!.event.listen(event, (e) => {
    handler(e);
  });
}

/**
 * 发送 Tauri 事件
 */
export async function emitTauriEvent(event: string, payload?: unknown): Promise<void> {
  if (!isTauriEnvironment()) {
    throw new Error('Not running in Tauri environment');
  }

  await window.__TAURI__!.event.emit(event, payload);
}

/**
 * 获取后端 API 基础 URL
 *
 * Tauri 模式: http://127.0.0.1:8080
 * Sandbox 模式: 从环境变量或配置获取
 */
export function getBackendBaseUrl(): string {
  if (isTauriEnvironment()) {
    return 'http://127.0.0.1:8080';
  }

  return normalizeConfiguredBaseUrl(process.env.NEXT_PUBLIC_API_URL, DEFAULT_TAURI_BACKEND_BASE_URL);
}
