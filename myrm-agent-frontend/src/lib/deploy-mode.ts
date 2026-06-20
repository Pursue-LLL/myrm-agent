/**
 * [INPUT]
 * - window.localStorage (POS: 客户端部署模式覆盖存储)
 * - process.env.NEXT_PUBLIC_DEPLOY_MODE / NEXT_PUBLIC_API_BASE_URL / NEXT_PUBLIC_BACKEND_BASE_URL (POS: 前端运行时配置)
 *
 * [OUTPUT]
 * - isTauriRuntime: Tauri 运行时判定。
 * - getDeployMode: 解析当前前端部署模式。
 * - isLocalMode: 判断是否处于本地模式。
 * - getApiBaseUrl: 返回安全的 API 基础地址。
 * - getBackendBaseUrl: 返回安全的后端基础地址。
 * - getDocsUrl: 返回文档站外链。
 * - normalizeConfiguredBaseUrl: 规范化并校验配置的 URL。
 *
 * [POS]
 * 前端部署模式与基础地址解析层。统一判定本地、桌面和沙箱环境，并阻断 `undefined` 之类的脏配置进入请求链路。
 */
/**
 * 前端运行环境检测工具
 *
 * 前端运行环境（注意：与后端 DEPLOY_MODE 是两个独立概念）：
 * - TAURI: Tauri 桌面客户端 WebView（后端 DEPLOY_MODE=local）
 * - LOCAL: 浏览器独立访问 WebUI（后端 DEPLOY_MODE=local）
 * - SANDBOX: 沙箱模式（后端 DEPLOY_MODE=sandbox）
 *
 * TAURI 和 LOCAL 统称"本地模式"，共享相同的前端行为（本地后端、本地存储）。
 * 使用 isLocalMode() 判断是否为本地模式。
 *
 * ## 配置方式
 *
 * 通过环境变量 `NEXT_PUBLIC_DEPLOY_MODE` 配置（推荐）：
 * - `.env.local`: `NEXT_PUBLIC_DEPLOY_MODE=sandbox` 或 `tauri` 或 `local`
 * - 构建时注入: `NEXT_PUBLIC_DEPLOY_MODE=tauri npm run build`
 *
 * ## 检测优先级（从高到低）
 *
 * 1. **开发者模式覆盖**（localStorage: `dev-mode-storage`）
 *    - 用于本地开发测试不同模式
 *    - 优先级最高，便于调试
 *
 * 2. **环境变量**（`NEXT_PUBLIC_DEPLOY_MODE`）
 *    - 构建时或运行时配置
 *    - 标准的 12-Factor App 配置方式
 *    - SaaS：`NEXT_PUBLIC_API_BASE_URL=https://<cp-host>/proxy/me/api/v1`
 *
 * 3. **默认值**：tauri（Tauri 桌面客户端的 WebView 环境）
 */

export type DeployMode = 'tauri' | 'local' | 'sandbox';

const LOCAL_MODES: ReadonlySet<DeployMode> = new Set(['tauri', 'local']);
const FALLBACK_API_BASE_URL = 'http://127.0.0.1:8080/api/v1';
const FALLBACK_BACKEND_BASE_URL = 'http://127.0.0.1:8080';
/** Desktop sidecar default; mirrors BackendConfig when enable_webui_mode=false. */
const TAURI_DESKTOP_API_PORT = 8080;
/** WebUI sidecar default; mirrors SystemConfig.api_port when enable_webui_mode=true. */
const TAURI_WEBUI_API_PORT = 25808;
const INVALID_BASE_URL_VALUES = new Set(['undefined', 'null']);

export function normalizeConfiguredBaseUrl(value: string | null | undefined, fallback: string): string {
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

/**
 * 获取开发者模式覆盖状态（仅客户端）
 * 使用函数而非直接导入，避免 SSR 时的 localStorage 访问问题
 */
function getDevModeOverride(): { enabled: boolean; override: string } | null {
  if (typeof window === 'undefined') return null;

  try {
    const stored = localStorage.getItem('dev-mode-storage');
    if (stored) {
      const parsed = JSON.parse(stored);
      // Zustand v4+ persist 使用 {state: {...}, version: 0} 格式
      // 兼容旧格式（直接存储 state）
      return parsed.state || parsed || null;
    }
  } catch (error) {
    console.error('Failed to read dev mode override:', error);
  }

  return null;
}

/**
 * 检测是否运行在 Tauri 桌面端（基于 window.__TAURI__ 运行时检测，不受配置覆盖影响）
 */
export function isTauriRuntime(): boolean {
  if (typeof window === 'undefined') return false;
  return '__TAURI__' in window;
}

const VALID_MODES: ReadonlySet<string> = new Set<DeployMode>(['tauri', 'local', 'sandbox']);

function isValidDeployMode(value: string): value is DeployMode {
  return VALID_MODES.has(value);
}

/**
 * 从环境变量获取部署模式
 */
function getDeployModeFromEnv(): DeployMode | null {
  const envMode = process.env.NEXT_PUBLIC_DEPLOY_MODE;
  if (envMode && isValidDeployMode(envMode)) {
    return envMode;
  }
  return null;
}

/**
 * 是否为本地模式（TAURI 或 LOCAL）
 *
 * 本地模式共享相同的前端行为：使用本地后端、本地存储、单用户。
 */
export function isLocalMode(): boolean {
  return LOCAL_MODES.has(getDeployMode());
}

/**
 * 获取当前部署模式
 *
 * 检测优先级：显式 sandbox 构建 > 开发者模式覆盖 > 环境变量 > 默认 tauri
 */
export function getDeployMode(): DeployMode {
  if (typeof window === 'undefined') {
    return getDeployModeFromEnv() ?? 'tauri';
  }

  const envMode = getDeployModeFromEnv();
  if (envMode === 'sandbox') {
    return 'sandbox';
  }

  const devMode = getDevModeOverride();
  if (devMode?.enabled && isValidDeployMode(devMode.override)) {
    return devMode.override;
  }

  if (envMode) return envMode;

  return 'tauri';
}

/**
 * 检测是否为 Sandbox 模式
 */
export function isSandbox(): boolean {
  return getDeployMode() === 'sandbox';
}

/**
 * SaaS/sandbox CP auth UI for this build (compile-time env only).
 * Dev-mode localStorage override must not hide OAuth on sandbox dev servers.
 */
export function isSandboxAuthBuild(): boolean {
  return process.env.NEXT_PUBLIC_DEPLOY_MODE === 'sandbox';
}

/** Redirect to /auth/login only for hosted sandbox builds (CP auth), not local/tauri. */
export function shouldRedirectToLoginOnAuthFailure(): boolean {
  return isSandboxAuthBuild();
}

/**
 * 检查是否启用了开发者模式覆盖
 */
export function isDevModeOverrideEnabled(): boolean {
  const devMode = getDevModeOverride();
  return devMode?.enabled === true && devMode.override !== 'none';
}

/**
 * 获取本地模式下的固定用户 ID
 *
 * 本地模式（TAURI/LOCAL）为单用户，使用固定 ID 与后端 API 保持一致。
 */
export function getLocalUserId(): string {
  return 'local_user';
}

/**
 * Resolve Tauri backend port from persisted system config (if WebUI mode), else desktop default.
 */
function getTauriBackendPort(): number {
  if (typeof window === 'undefined') {
    return TAURI_DESKTOP_API_PORT;
  }

  try {
    const storage = window.localStorage;
    const raw = storage.getItem('myrm-tauri-system-config');
    if (raw) {
      const parsed = JSON.parse(raw) as { enableWebUIMode?: boolean; apiPort?: number };
      if (parsed.enableWebUIMode) {
        return parsed.apiPort ?? TAURI_WEBUI_API_PORT;
      }
    }
  } catch {
    // ignore malformed cache
  }

  return TAURI_DESKTOP_API_PORT;
}

/**
 * Get API base URL
 *
 * 本地模式: 使用本地服务 (127.0.0.1:8080)
 * Tauri Desktop: 8080（与 Rust BackendConfig 桌面模式一致）
 * Tauri WebUI: apiPort（默认 25808）
 * Sandbox 模式: 使用环境变量配置的远程服务
 */
export function getApiBaseUrl(): string {
  if (isTauriRuntime()) {
    return `http://127.0.0.1:${getTauriBackendPort()}/api/v1`;
  }
  if (isLocalMode()) {
    return '/api/v1';
  }
  return normalizeConfiguredBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL, FALLBACK_API_BASE_URL);
}

/**
 * 获取后端基础 URL（不含 API 路径前缀）
 */
export function getBackendBaseUrl(): string {
  if (isTauriRuntime()) {
    return `http://127.0.0.1:${getTauriBackendPort()}`;
  }
  if (isLocalMode()) {
    return '';
  }
  return normalizeConfiguredBaseUrl(process.env.NEXT_PUBLIC_BACKEND_BASE_URL, FALLBACK_BACKEND_BASE_URL);
}

/** Documentation site base URL (Mintlify). */
export function getDocsUrl(path: string = '/'): string {
  const base = normalizeConfiguredBaseUrl(process.env.NEXT_PUBLIC_DOCS_URL, 'https://docs.myrm.ai');
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${normalizedPath === '/' ? '' : normalizedPath}`;
}
