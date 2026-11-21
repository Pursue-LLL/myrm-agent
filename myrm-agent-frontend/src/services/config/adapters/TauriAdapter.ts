/**
 * [INPUT]
 * - `@/lib/deploy-mode` (`getApiBaseUrl`)
 * - `@/lib/backend-health` (`markLocalBackendUnreachable`) (POS: tells the app the local backend is down)
 * - `@/lib/platform-readiness` (`whenDatabaseReady`) (POS: whether the local database is up)
 * - `./BaseAdapter` BaseConfigAdapter / BACKEND_NOT_AVAILABLE_ERROR / backendUnavailableSyncResult / isTransportFailure (POS: the failure answer both adapters share)
 *
 * [OUTPUT]
 * - `TauriConfigAdapter`: local/Tauri 配置 HTTP 适配（含 Next 代理 5xx → offline 语义）
 *
 * [POS]
 * 本地模式配置同步适配器。WebUI 经 `/api/v1` 代理；Tauri 可直连 sidecar。与 `ConfigSyncManager` 离线队列配合。
 * 后端不可用（Next 代理 500/502/503/504、请求失败、超时、数据库未就绪）时：`getAll` / `get` 抛错，不把「不知道」
 * 答成「没有这一行」；`sync` 返回 `backendUnavailableSyncResult()` 供同步层保留重试。请求失败只在 `fetch()` 调用处
 * 判定，处理应答时的 `TypeError` 属于缺陷，照常抛出。
 */

import { markLocalBackendUnreachable } from '@/lib/backend-health';
import { getApiBaseUrl } from '@/lib/deploy-mode';
import { whenDatabaseReady } from '@/lib/platform-readiness';
import {
  BACKEND_NOT_AVAILABLE_ERROR,
  BaseConfigAdapter,
  backendUnavailableSyncResult,
  isTransportFailure,
} from './BaseAdapter';
import type { ConfigKey, ConfigRecord, ConfigChange, SyncResult, ConfigVersion, ConfigValueMap } from '../types';
import { ConfigConflictError, ConfigSyncError } from '../types';

/**
 * 后端 API 响应类型
 */
interface ApiConfigResponse<K extends ConfigKey = ConfigKey> {
  key: K;
  value: ConfigValueMap[K];
  version: ConfigVersion;
  updatedAt: string;
  deviceId: string;
  isSystemDefault?: boolean;
  unreadable?: boolean;
}

interface ApiAllConfigsResponse {
  configs: Record<string, ApiConfigResponse>;
}

interface ApiSyncResponse {
  success: boolean;
  conflicts: ConfigKey[];
  newVersions: Record<string, ConfigVersion>;
  error?: string;
}

/** Next.js rewrite proxy and gateway errors when local backend is down. */
const BACKEND_UNAVAILABLE_HTTP_STATUSES = new Set([500, 502, 503, 504]);

/** The request did not reach the local backend: database not ready, request failed, or timed out. */
class BackendUnavailableError extends Error {
  constructor() {
    super(BACKEND_NOT_AVAILABLE_ERROR);
    this.name = 'BackendUnavailableError';
  }
}

/**
 * Tauri 配置适配器
 */
export class TauriConfigAdapter extends BaseConfigAdapter {
  private get baseUrl(): string {
    return getApiBaseUrl();
  }

  protected override initDeviceId(): string {
    return 'tauri-local';
  }

  /**
   * 统一 fetch，自动携带 Cookie 以兼容 WebUI Remote 模式的 JWT 认证。
   * 非 Remote 模式下后端跳过认证，Cookie 虽携带但无影响。
   * 内置 10s 超时防止后端卡死时前端无限等待。
   */
  private async localFetch(url: string, init?: RequestInit): Promise<Response> {
    const ready = await whenDatabaseReady();
    if (!ready) {
      throw new BackendUnavailableError();
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10_000);

    let response: Response;
    try {
      response = await fetch(url, {
        ...init,
        credentials: 'include',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...init?.headers,
        },
      });
    } catch (error) {
      if (isTransportFailure(error)) {
        markLocalBackendUnreachable();
        throw new BackendUnavailableError();
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }

    if (this.isBackendUnavailableStatus(response.status)) {
      markLocalBackendUnreachable();
    }
    return response;
  }

  private isBackendUnavailableStatus(status: number): boolean {
    return BACKEND_UNAVAILABLE_HTTP_STATUSES.has(status);
  }

  /**
   * 获取配置
   */
  async getAll(keys?: readonly ConfigKey[]): Promise<Map<ConfigKey, ConfigRecord>> {
    try {
      const url = keys?.length
        ? `${this.baseUrl}/config?keys=${encodeURIComponent(keys.join(','))}`
        : `${this.baseUrl}/config`;
      const response = await this.localFetch(url);

      if (!response.ok) {
        if (response.status === 404) {
          return new Map();
        }
        if (this.isBackendUnavailableStatus(response.status)) {
          console.warn('[TauriAdapter] Backend not available, will retry via ConfigSyncManager');
          throw new ConfigSyncError(BACKEND_NOT_AVAILABLE_ERROR);
        }
        throw new ConfigSyncError(`Failed to get all configs: ${response.statusText}`);
      }

      const data: ApiAllConfigsResponse = await response.json();
      const result = new Map<ConfigKey, ConfigRecord>();

      for (const [key, record] of Object.entries(data.configs)) {
        result.set(key as ConfigKey, this.toConfigRecord(record as ApiConfigResponse));
      }

      return result;
    } catch (error) {
      if (error instanceof BackendUnavailableError) {
        console.warn('[TauriAdapter] Backend not available, will retry via ConfigSyncManager');
        throw new ConfigSyncError(BACKEND_NOT_AVAILABLE_ERROR);
      }
      throw error;
    }
  }

  /**
   * 获取单个配置
   */
  async get<K extends ConfigKey>(key: K): Promise<ConfigRecord<K> | null> {
    try {
      const response = await this.localFetch(`${this.baseUrl}/config/${key}`);

      if (response.status === 404) {
        return null;
      }

      if (!response.ok) {
        if (this.isBackendUnavailableStatus(response.status)) {
          console.warn(`[TauriAdapter] Backend not available, cannot read '${key}'`);
          throw new ConfigSyncError(BACKEND_NOT_AVAILABLE_ERROR);
        }
        throw new ConfigSyncError(`Failed to get config '${key}': ${response.statusText}`);
      }

      const data: ApiConfigResponse<K> = await response.json();
      return this.toConfigRecord(data);
    } catch (error) {
      if (error instanceof BackendUnavailableError) {
        console.warn(`[TauriAdapter] Backend not available, cannot read '${key}'`);
        throw new ConfigSyncError(BACKEND_NOT_AVAILABLE_ERROR);
      }
      throw error;
    }
  }

  /**
   * 设置配置（带乐观锁）
   */
  async set<K extends ConfigKey>(
    key: K,
    value: ConfigValueMap[K],
    expectedVersion?: ConfigVersion,
  ): Promise<ConfigRecord<K>> {
    try {
      const response = await this.localFetch(`${this.baseUrl}/config/${key}`, {
        method: 'PUT',
        body: JSON.stringify({
          value,
          expectedVersion,
          deviceId: this.deviceId,
        }),
      });

      if (response.status === 409) {
        const errorData = await response.json();
        throw new ConfigConflictError(key, expectedVersion ?? '0_0', errorData.serverVersion ?? '0_0');
      }

      if (!response.ok) {
        if (this.isBackendUnavailableStatus(response.status)) {
          console.warn(`[TauriAdapter] Backend not available, skipping set '${key}'`);
          return this.createRecord(key, value, expectedVersion);
        }
        throw new ConfigSyncError(`Failed to set config '${key}': ${response.statusText}`);
      }

      const data: ApiConfigResponse<K> = await response.json();
      return this.toConfigRecord(data);
    } catch (error) {
      if (error instanceof BackendUnavailableError) {
        console.warn(`[TauriAdapter] Backend not available, skipping set '${key}'`);
        return this.createRecord(key, value, expectedVersion);
      }
      throw error;
    }
  }

  /**
   * 删除配置
   */
  async delete(key: ConfigKey): Promise<boolean> {
    try {
      const response = await this.localFetch(`${this.baseUrl}/config/${key}`, {
        method: 'DELETE',
      });

      if (response.status === 404) {
        return false;
      }

      if (!response.ok) {
        if (this.isBackendUnavailableStatus(response.status)) {
          console.warn(`[TauriAdapter] Backend not available, skipping delete '${key}'`);
          return false;
        }
        throw new ConfigSyncError(`Failed to delete config '${key}': ${response.statusText}`);
      }

      return true;
    } catch (error) {
      if (error instanceof BackendUnavailableError) {
        console.warn(`[TauriAdapter] Backend not available, skipping delete '${key}'`);
        return false;
      }
      throw error;
    }
  }

  /**
   * 批量同步
   */
  async sync(changes: ConfigChange[]): Promise<SyncResult> {
    if (changes.length === 0) {
      return {
        success: true,
        conflicts: [],
        newVersions: new Map(),
      };
    }

    try {
      const response = await this.localFetch(`${this.baseUrl}/config/sync`, {
        method: 'POST',
        body: JSON.stringify({
          changes,
          deviceId: this.deviceId,
        }),
      });

      if (!response.ok) {
        if (this.isBackendUnavailableStatus(response.status)) {
          console.warn('[TauriAdapter] Backend not available, sync failed');
          return backendUnavailableSyncResult();
        }
        throw new ConfigSyncError(`Failed to sync configs: ${response.statusText}`);
      }

      const data: ApiSyncResponse = await response.json();

      return {
        success: data.success,
        conflicts: data.conflicts,
        newVersions: new Map(Object.entries(data.newVersions)) as Map<ConfigKey, string>,
        error: data.error,
      };
    } catch (error) {
      if (error instanceof BackendUnavailableError) {
        console.warn('[TauriAdapter] Backend not available, sync failed');
        return backendUnavailableSyncResult();
      }
      throw error;
    }
  }

  /**
   * 转换 API 响应为 ConfigRecord
   */
  private toConfigRecord<K extends ConfigKey>(data: ApiConfigResponse<K>): ConfigRecord<K> {
    return {
      key: data.key,
      value: data.value,
      meta: {
        version: data.version,
        updatedAt: data.updatedAt,
        deviceId: data.deviceId,
      },
      isSystemDefault: data.isSystemDefault,
      unreadable: data.unreadable,
    };
  }
}
