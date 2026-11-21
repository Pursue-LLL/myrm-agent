/**
 * [INPUT]
 * - `../types` ConfigAdapter / SyncResult / createInitialVersion / incrementVersion (POS: adapter contract, backend answer, version arithmetic)
 *
 * [OUTPUT]
 * BaseConfigAdapter: device id, version helpers and the abstract adapter surface.
 * BACKEND_NOT_AVAILABLE_ERROR / backendUnavailableSyncResult: the failed `SyncResult` of a write that never reached a backend.
 * isTransportFailure: whether a rejected `fetch()` call is a delivery failure rather than a bug.
 *
 * [POS]
 * What the Tauri and Sandbox adapters share. Both answer a reachability failure the same way, because the sync layer
 * keeps a write for a later retry only when it sees this result: reads (`getAll` / `get`) throw, so "unknown" is never
 * mistaken for "no such row", and `sync` returns the failed result instead of throwing. Whatever else a backend refuses
 * is an error the caller sees.
 */

import type {
  ConfigAdapter,
  ConfigKey,
  ConfigRecord,
  ConfigChange,
  SyncResult,
  ConfigVersion,
  ConfigValueMap,
} from '../types';
import { createInitialVersion, incrementVersion } from '../types';

/** `SyncResult.error` of a write that did not reach a backend that could take it; `isRecoverableSyncError` matches it. */
export const BACKEND_NOT_AVAILABLE_ERROR = 'Backend not available';

export function backendUnavailableSyncResult(): SyncResult {
  return {
    success: false,
    conflicts: [],
    newVersions: new Map<ConfigKey, ConfigVersion>(),
    error: BACKEND_NOT_AVAILABLE_ERROR,
  };
}

/**
 * A `fetch()` that produced no response: offline, DNS or TLS failure (a `TypeError` in every browser, whatever its
 * wording) or the adapter's own timeout abort. Apply it to the `fetch()` call only; a `TypeError` from handling the
 * answer is a bug and must stay visible.
 */
export function isTransportFailure(error: unknown): boolean {
  return error instanceof TypeError || (error instanceof DOMException && error.name === 'AbortError');
}

/**
 * 适配器基类
 *
 * 提供：
 * - 设备 ID 管理
 * - 版本号生成
 * - 通用工具方法
 */
export abstract class BaseConfigAdapter implements ConfigAdapter {
  protected deviceId: string;

  constructor() {
    this.deviceId = this.initDeviceId();
  }

  /**
   * 初始化设备 ID
   * 子类可重写以提供不同的设备 ID 策略
   */
  protected initDeviceId(): string {
    if (typeof window === 'undefined') {
      return 'server';
    }

    let id = localStorage.getItem('config-device-id');
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem('config-device-id', id);
    }
    return id;
  }

  /**
   * 获取设备 ID
   */
  getDeviceId(): string {
    return this.deviceId;
  }

  /**
   * 创建新的配置记录
   */
  protected createRecord<K extends ConfigKey>(
    key: K,
    value: ConfigValueMap[K],
    existingVersion?: ConfigVersion,
  ): ConfigRecord<K> {
    const version = existingVersion ? incrementVersion(existingVersion) : createInitialVersion();

    return {
      key,
      value,
      meta: {
        version,
        updatedAt: new Date().toISOString(),
        deviceId: this.deviceId,
      },
    };
  }

  // ============================================================================
  // 抽象方法 - 子类必须实现
  // ============================================================================

  abstract getAll(keys?: readonly ConfigKey[]): Promise<Map<ConfigKey, ConfigRecord>>;

  abstract get<K extends ConfigKey>(key: K): Promise<ConfigRecord<K> | null>;

  abstract set<K extends ConfigKey>(
    key: K,
    value: ConfigValueMap[K],
    expectedVersion?: ConfigVersion,
  ): Promise<ConfigRecord<K>>;

  abstract delete(key: ConfigKey): Promise<boolean>;

  abstract sync(changes: ConfigChange[]): Promise<SyncResult>;
}
