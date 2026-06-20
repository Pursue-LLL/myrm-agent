/**
 * 本地模式配置适配器（Tauri Desktop / Local CLI / WebUI）
 *
 * 通过 HTTP API 与本地 Python Sidecar 的 SQLite 数据库交互。
 * Desktop 和 WebUI 共享同一数据库。
 *
 * 特点：
 * - 低延迟（本地网络）
 * - 明文存储（操作系统级安全）
 * - 自动携带 Cookie（兼容 WebUI Remote 的 JWT 认证）
 */

import { getApiBaseUrl } from '@/lib/deploy-mode';
import { BaseConfigAdapter } from './BaseAdapter';
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
  private localFetch(url: string, init?: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10_000);

    return fetch(url, {
      ...init,
      credentials: 'include',
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...init?.headers,
      },
    }).finally(() => clearTimeout(timeoutId));
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
        throw new ConfigSyncError(`Failed to get all configs: ${response.statusText}`);
      }

      const data: ApiAllConfigsResponse = await response.json();
      const result = new Map<ConfigKey, ConfigRecord>();

      for (const [key, record] of Object.entries(data.configs)) {
        result.set(key as ConfigKey, this.toConfigRecord(record as ApiConfigResponse));
      }

      return result;
    } catch (error) {
      // 网络错误（后端未运行）视为正常情况
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        console.warn('[TauriAdapter] Backend not available, returning empty configs');
        return new Map();
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
        throw new ConfigSyncError(`Failed to get config '${key}': ${response.statusText}`);
      }

      const data: ApiConfigResponse<K> = await response.json();
      return this.toConfigRecord(data);
    } catch (error) {
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        console.warn(`[TauriAdapter] Backend not available, skipping get '${key}'`);
        return null;
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
        throw new ConfigSyncError(`Failed to set config '${key}': ${response.statusText}`);
      }

      const data: ApiConfigResponse<K> = await response.json();
      return this.toConfigRecord(data);
    } catch (error) {
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        console.warn(`[TauriAdapter] Backend not available, skipping set '${key}'`);
        // 返回一个本地生成的记录（乐观更新）
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
        throw new ConfigSyncError(`Failed to delete config '${key}': ${response.statusText}`);
      }

      return true;
    } catch (error) {
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
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
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        console.warn('[TauriAdapter] Backend not available, sync failed');
        return {
          success: false,
          conflicts: [],
          newVersions: new Map<ConfigKey, string>(),
          error: 'Backend not available',
        };
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
    };
  }
}
