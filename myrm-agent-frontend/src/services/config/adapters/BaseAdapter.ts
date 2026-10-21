/**
 * 配置适配器基类
 *
 * 提供通用的工具方法和默认实现
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
