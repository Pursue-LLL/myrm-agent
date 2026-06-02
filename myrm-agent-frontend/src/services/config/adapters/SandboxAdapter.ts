/**
 * Sandbox 模式配置适配器
 *
 * 通过 HTTP API 与云端 PostgreSQL 数据库交互。
 * 敏感数据由后端服务端加密（AES-256-GCM），前端无需关心加密。
 */

import { getAuthToken } from '@/lib/guest';
import { getApiBaseUrl } from '@/lib/deploy-mode';
import { BaseConfigAdapter } from './BaseAdapter';
import type { ConfigKey, ConfigRecord, ConfigChange, SyncResult, ConfigVersion, ConfigValueMap } from '../types';
import { ConfigSyncError } from '../types';

interface ApiConfigResponse<K extends ConfigKey = ConfigKey> {
  key: K;
  value: ConfigValueMap[K];
  version: ConfigVersion;
  updatedAt: string;
  deviceId: string;
  encrypted: boolean;
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

export class SandboxConfigAdapter extends BaseConfigAdapter {
  async getAll(keys?: readonly ConfigKey[]): Promise<Map<ConfigKey, ConfigRecord>> {
    const url = keys?.length ? `/config?keys=${encodeURIComponent(keys.join(','))}` : '/config';
    const response = await this.authFetch(url);

    if (!response.ok) {
      if (response.status === 401) {
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
  }

  async get<K extends ConfigKey>(key: K): Promise<ConfigRecord<K> | null> {
    const response = await this.authFetch(`/config/${key}`);

    if (response.status === 404 || response.status === 401) {
      return null;
    }

    if (!response.ok) {
      throw new ConfigSyncError(`Failed to get config '${key}': ${response.statusText}`);
    }

    const data: ApiConfigResponse<K> = await response.json();
    return this.toConfigRecord(data);
  }

  async set<K extends ConfigKey>(
    key: K,
    value: ConfigValueMap[K],
    expectedVersion?: ConfigVersion,
  ): Promise<ConfigRecord<K>> {
    const response = await this.authFetch(`/config/${key}`, {
      method: 'PUT',
      body: JSON.stringify({
        value,
        expectedVersion,
        deviceId: this.deviceId,
      }),
    });

    if (response.status === 409) {
      const { ConfigConflictError } = await import('../types');
      const errorData = await response.json();
      throw new ConfigConflictError(key, expectedVersion ?? '0_0', errorData.serverVersion ?? '0_0');
    }

    if (!response.ok) {
      throw new ConfigSyncError(`Failed to set config '${key}': ${response.statusText}`);
    }

    const data: ApiConfigResponse<K> = await response.json();
    return this.toConfigRecord(data);
  }

  async delete(key: ConfigKey): Promise<boolean> {
    const response = await this.authFetch(`/config/${key}`, {
      method: 'DELETE',
    });

    if (response.status === 404) {
      return false;
    }

    if (!response.ok) {
      throw new ConfigSyncError(`Failed to delete config '${key}': ${response.statusText}`);
    }

    return true;
  }

  async sync(changes: ConfigChange[]): Promise<SyncResult> {
    if (changes.length === 0) {
      return {
        success: true,
        conflicts: [],
        newVersions: new Map(),
      };
    }

    const response = await this.authFetch('/config/sync', {
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
  }

  private toConfigRecord<K extends ConfigKey>(data: ApiConfigResponse<K>): ConfigRecord<K> {
    return {
      key: data.key,
      value: data.value as ConfigValueMap[K],
      meta: {
        version: data.version,
        updatedAt: data.updatedAt,
        deviceId: data.deviceId,
      },
      encrypted: data.encrypted,
    };
  }

  private async authFetch(path: string, options?: RequestInit): Promise<Response> {
    const token = getAuthToken();
    if (!token) {
      return new Response(null, { status: 401, statusText: 'Unauthorized' });
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10_000);

    const baseUrl = getApiBaseUrl();
    return fetch(`${baseUrl}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        ...options?.headers,
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
    }).finally(() => clearTimeout(timeoutId));
  }
}
