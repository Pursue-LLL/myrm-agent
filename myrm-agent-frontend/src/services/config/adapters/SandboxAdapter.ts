/**
 * [INPUT]
 * - `@/lib/guest` getAuthToken (POS: the session's bearer token)
 * - `@/lib/deploy-mode` getApiBaseUrl (POS: cloud API origin)
 * - `./BaseAdapter` BaseConfigAdapter / backendUnavailableSyncResult / isTransportFailure (POS: the failure answer both adapters share)
 * - `../types` ConfigSyncError / record and change shapes (POS: adapter contract)
 *
 * [OUTPUT]
 * SandboxConfigAdapter: cloud configuration over the HTTP API (PostgreSQL, encrypted by the server).
 *
 * [POS]
 * Cloud-mode adapter of the sync layer. Sensitive values are encrypted by the server (AES-256-GCM); the frontend never
 * handles ciphertext. Only a 404 answers "no such row": a missing or expired token, an unreachable API and a server
 * error make `get` throw, so the sync layer can tell "absent" from "unknown". A `sync` that could not be delivered
 * (transport failure, 401, 408, 429, 502, 503, 504) returns `backendUnavailableSyncResult()`, which the sync layer
 * keeps for a retry; any other refusal (422, 500 ...) throws, because repeating the same write cannot succeed.
 */

import { getAuthToken } from '@/lib/guest';
import { getApiBaseUrl } from '@/lib/deploy-mode';
import { BaseConfigAdapter, backendUnavailableSyncResult, isTransportFailure } from './BaseAdapter';
import type { ConfigKey, ConfigRecord, ConfigChange, SyncResult, ConfigVersion, ConfigValueMap } from '../types';
import { ConfigSyncError } from '../types';

/** Statuses of an expired session, a request timeout, a rate limit or a gateway with no backend behind it. */
const UNDELIVERED_SYNC_STATUSES = new Set([401, 408, 429, 502, 503, 504]);

interface ApiConfigResponse<K extends ConfigKey = ConfigKey> {
  key: K;
  value: ConfigValueMap[K];
  version: ConfigVersion;
  updatedAt: string;
  deviceId: string;
  encrypted: boolean;
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

    if (response.status === 404) {
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

    let response: Response;
    try {
      response = await this.authFetch('/config/sync', {
        method: 'POST',
        body: JSON.stringify({
          changes,
          deviceId: this.deviceId,
        }),
      });
    } catch (error) {
      if (!isTransportFailure(error)) {
        throw error;
      }
      console.warn('[SandboxAdapter] Backend not reachable, sync failed:', error);
      return backendUnavailableSyncResult();
    }

    if (UNDELIVERED_SYNC_STATUSES.has(response.status)) {
      console.warn(`[SandboxAdapter] Backend not available (HTTP ${response.status}), sync failed`);
      return backendUnavailableSyncResult();
    }

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
      unreadable: data.unreadable,
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
