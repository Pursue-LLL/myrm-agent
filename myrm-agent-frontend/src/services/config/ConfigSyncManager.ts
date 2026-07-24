/**
 * 配置同步管理器
 *
 * 统一管理配置的加载、缓存、同步。
 *
 * 核心特性：
 * - 乐观更新：先更新 UI，再异步同步
 * - 防抖同步：避免频繁写入
 * - 离线支持：网络不可用时保存到本地队列
 * - 冲突检测：版本号乐观锁
 */

import { ensureLocalBackendReady } from '@/lib/backend-health';
import { isLocalMode } from '@/lib/deploy-mode';
import { ensurePlatformReadiness } from '@/lib/platform-readiness';
import { cloneDeep } from 'lodash-es';
import { withConfigInitLock } from './configInitLock';
import { valuesEqual } from './configFingerprint';
import {
  isNormalizedDirty,
  normalizeConfigValue,
  STARTUP_NORMALIZE_KEYS,
} from './configNormalizer';
import { threeWayMerge } from './mergeUtils';
import { BaseConfigAdapter, TauriConfigAdapter, SandboxConfigAdapter } from './adapters';
import type { ConfigAdapter, ConfigKey, ConfigRecord, ConfigChange, ConfigValueMap, SyncResult } from './types';
import { ALL_CONFIG_KEYS, CORE_CONFIG_KEYS, createInitialVersion, incrementVersion } from './types';

// 防抖延迟（毫秒）
const SYNC_DEBOUNCE_MS = 1000;

function isE2eSearchSyncBlocked(): boolean {
  return typeof window !== 'undefined' && Boolean(window.__MYRM_E2E_BLOCK_SEARCH_SYNC__);
}

function shouldSuppressE2eSearchInbound(key: ConfigKey): boolean {
  return key === 'searchServices' && isE2eSearchSyncBlocked();
}

const INIT_FETCH_MAX_ATTEMPTS = 3;
const INIT_FETCH_RETRY_DELAY_MS = 500;

// 离线队列存储键
const OFFLINE_QUEUE_KEY = 'config-offline-queue';

/**
 * 同步状态
 */
export type SyncStatus = 'idle' | 'loading' | 'syncing' | 'error' | 'offline';

/**
 * 配置变更监听器
 */
export type ConfigChangeListener<K extends ConfigKey = ConfigKey> = (
  key: K,
  value: ConfigValueMap[K],
  meta: ConfigRecord<K>['meta'],
) => void;

/**
 * 配置冲突上下文
 */
export interface ConfigConflictResolution {
  configKey: ConfigKey;
  localVersion: string;
  serverVersion: string;
  deviceId: string;
  localValue?: unknown;
  serverValue?: unknown;
}

/**
 * 冲突解决器
 */
export type ConfigConflictResolver = (conflict: ConfigConflictResolution) => Promise<boolean> | boolean;

/**
 * 配置同步管理器
 */
class ConfigSyncManager {
  private adapter: ConfigAdapter;
  private cache: Map<ConfigKey, ConfigRecord> = new Map();
  private baseCache: Map<ConfigKey, ConfigRecord> = new Map();
  private changeQueue: ConfigChange[] = [];
  private syncDebounceTimer: ReturnType<typeof setTimeout> | null = null;
  private listeners: Map<ConfigKey, Set<ConfigChangeListener>> = new Map();
  private conflictResolver: ConfigConflictResolver | null = null;
  private _status: SyncStatus = 'idle';
  private _isInitialized = false;
  private onlineHandlerRegistered = false;

  constructor() {
    this.adapter = this.createAdapter();
  }

  /**
   * 创建适配器（根据部署模式）
   */
  private createAdapter(): ConfigAdapter {
    return isLocalMode() ? new TauriConfigAdapter() : new SandboxConfigAdapter();
  }

  /**
   * 获取当前同步状态
   */
  get status(): SyncStatus {
    return this._status;
  }

  /**
   * 是否已初始化
   */
  get isInitialized(): boolean {
    return this._isInitialized;
  }

  /**
   * 初始化：从后端加载配置
   * Sandbox 模式：先加载核心配置以加快首屏，再后台预加载其余
   * Tauri 模式：一次性加载（本地低延迟）
   */
  async initialize(): Promise<Map<ConfigKey, ConfigRecord>> {
    if (this._isInitialized) {
      return this.cache;
    }

    this._status = 'loading';

    try {
      if (isLocalMode()) {
        const ready = await ensureLocalBackendReady();
        if (!ready) {
          this._status = 'offline';
          this.registerOnlineHandler();
          void ensurePlatformReadiness().then((snapshot) => {
            if (snapshot.database && !this._isInitialized) {
              void this.initialize();
            }
          });
          return this.cache;
        }
      }

      const offlineChanges = this.loadOfflineQueue();
      const useProgressiveLoad = !isLocalMode() && this.adapter instanceof SandboxConfigAdapter;

      if (useProgressiveLoad) {
        const coreConfigs = await this.fetchAllWithRetry(() => this.adapter.getAll(CORE_CONFIG_KEYS));
        this.cache = coreConfigs;
        this.baseCache = cloneDeep(coreConfigs);
        this._isInitialized = true;
        this._status = 'idle';

        const remainingKeys = ALL_CONFIG_KEYS.filter((k) => !CORE_CONFIG_KEYS.includes(k));
        if (remainingKeys.length > 0) {
          this.adapter.getAll(remainingKeys).then(
            (rest) => {
              for (const [k, v] of rest) {
                this.cache.set(k, v);
                this.baseCache.set(k, cloneDeep(v));
              }
            },
            (err) => {
              console.warn('[ConfigSync] Background preload failed:', err);
            },
          );
        }
      } else {
        const configs = await this.fetchAllWithRetry(() => this.adapter.getAll());
        this.cache = configs;
        this.baseCache = cloneDeep(configs);
        this._isInitialized = true;
        this._status = 'idle';
      }

      if (offlineChanges.length > 0) {
        console.warn(`[ConfigSync] Found ${offlineChanges.length} offline changes, syncing...`);
        this.changeQueue = offlineChanges;
        await this.flushSync();
      }

      this.registerOnlineHandler();

      return this.cache;
    } catch (error) {
      console.warn('[ConfigSync] Initialization failed:', error);
      this._status = 'error';
      throw error;
    }
  }

  private async fetchAllWithRetry(
    fetchFn: () => Promise<Map<ConfigKey, ConfigRecord>>,
  ): Promise<Map<ConfigKey, ConfigRecord>> {
    let lastError: unknown;

    for (let attempt = 0; attempt < INIT_FETCH_MAX_ATTEMPTS; attempt += 1) {
      try {
        return await fetchFn();
      } catch (error) {
        lastError = error;
        if (attempt < INIT_FETCH_MAX_ATTEMPTS - 1) {
          await new Promise((resolve) => setTimeout(resolve, INIT_FETCH_RETRY_DELAY_MS));
        }
      }
    }

    throw lastError;
  }

  /**
   * 获取配置（优先缓存）
   */
  get<K extends ConfigKey>(key: K): ConfigValueMap[K] | null {
    const record = this.cache.get(key) as ConfigRecord<K> | undefined;
    return record?.value ?? null;
  }

  /**
   * 获取配置记录（包含元数据）
   */
  getRecord<K extends ConfigKey>(key: K): ConfigRecord<K> | null {
    return (this.cache.get(key) as ConfigRecord<K>) ?? null;
  }

  /**
   * 设置冲突解决器
   */
  setConflictResolver(resolver: ConfigConflictResolver | null): void {
    this.conflictResolver = resolver;
  }

  /**
   * 仅当内容与 baseCache 不同时才写入并同步。
   * 用于启动迁移，避免无意义的版本 bump 和冲突。
   */
  commitIfDirty<K extends ConfigKey>(key: K, value: ConfigValueMap[K]): boolean {
    const base = this.baseCache.get(key);
    if (base && valuesEqual(base.value, value)) {
      return false;
    }
    this.set(key, value);
    return true;
  }

  /**
   * 启动时归一化迁移（Web Lock 保证单 tab 写入）。
   * 在 initialize() 之后、Store hydrate 之前调用。
   */
  async runStartupNormalization(): Promise<void> {
    await withConfigInitLock(async () => {
      for (const key of STARTUP_NORMALIZE_KEYS) {
        const record = this.cache.get(key);
        if (!record) {
          continue;
        }

        const normalized = normalizeConfigValue(key, record.value as ConfigValueMap[typeof key]);
        if (normalized === null) {
          continue;
        }

        const base = this.baseCache.get(key);
        if (!isNormalizedDirty(key, base?.value as ConfigValueMap[typeof key], record.value as ConfigValueMap[typeof key])) {
          continue;
        }

        this.commitIfDirty(key, normalized);
      }
    });
  }

  /**
   * 设置配置（乐观更新 + 异步同步）
   */
  set<K extends ConfigKey>(key: K, value: ConfigValueMap[K]): void {
    if (
      typeof window !== 'undefined' &&
      window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ &&
      key === 'searchServices'
    ) {
      this.changeQueue = this.changeQueue.filter((change) => change.key !== 'searchServices');
      const current = this.cache.get(key) as ConfigRecord<K> | undefined;
      const currentVersion = current?.meta.version ?? createInitialVersion();
      const newRecord: ConfigRecord<K> = {
        key,
        value,
        meta: {
          version: incrementVersion(currentVersion),
          updatedAt: new Date().toISOString(),
          deviceId: (this.adapter as BaseConfigAdapter).getDeviceId(),
        },
      };
      this.cache.set(key, newRecord as ConfigRecord);
      this.notifyListeners(key, value, newRecord.meta);
      return;
    }

    const current = this.cache.get(key) as ConfigRecord<K> | undefined;
    const currentVersion = current?.meta.version ?? createInitialVersion();
    const newVersion = incrementVersion(currentVersion);

    // 1. 乐观更新缓存
    const newRecord: ConfigRecord<K> = {
      key,
      value,
      meta: {
        version: newVersion,
        updatedAt: new Date().toISOString(),
        deviceId: (this.adapter as BaseConfigAdapter).getDeviceId(),
      },
    };
    this.cache.set(key, newRecord as ConfigRecord);

    // 2. 通知监听器
    this.notifyListeners(key, value, newRecord.meta);

    // 3. 记录待同步变更
    this.changeQueue.push({
      key,
      value,
      expectedVersion: currentVersion,
      timestamp: Date.now(),
    });

    // 4. 防抖同步
    this.scheduleSyncDebounced();
  }

  /**
   * 删除配置
   */
  async delete(key: ConfigKey): Promise<boolean> {
    const success = await this.adapter.delete(key);
    if (success) {
      this.cache.delete(key);
      this.baseCache.delete(key);
    }
    return success;
  }

  /**
   * 订阅配置变更
   */
  subscribe<K extends ConfigKey>(key: K, listener: ConfigChangeListener<K>): () => void {
    if (!this.listeners.has(key)) {
      this.listeners.set(key, new Set());
    }
    this.listeners.get(key)!.add(listener as ConfigChangeListener);

    // 返回取消订阅函数
    return () => {
      this.listeners.get(key)?.delete(listener as ConfigChangeListener);
    };
  }

  /**
   * 强制立即同步
   */
  async forceSync(): Promise<SyncResult> {
    if (this.syncDebounceTimer) {
      clearTimeout(this.syncDebounceTimer);
      this.syncDebounceTimer = null;
    }
    return this.flushSync();
  }

  /**
   * 防抖同步
   */
  private scheduleSyncDebounced(): void {
    if (this.syncDebounceTimer) {
      clearTimeout(this.syncDebounceTimer);
    }

    this.syncDebounceTimer = setTimeout(() => {
      this.flushSync();
    }, SYNC_DEBOUNCE_MS);
  }

  /**
   * 立即同步所有待处理变更
   */
  private async flushSync(): Promise<SyncResult> {
    if (
      typeof window !== 'undefined' &&
      window.__MYRM_E2E_BLOCK_SEARCH_SYNC__
    ) {
      this.changeQueue = this.changeQueue.filter((change) => change.key !== 'searchServices');
    }
    if (this.changeQueue.length === 0) {
      return {
        success: true,
        conflicts: [],
        newVersions: new Map(),
      };
    }

    // 合并同一 key 的连续变更，取最后一个
    const mergedChanges = this.mergeChanges(this.changeQueue);
    this.changeQueue = [];

    this._status = 'syncing';

    try {
      const result = await this.adapter.sync(mergedChanges);

      if (result.success) {
        // 清空离线队列
        this.clearOfflineQueue();

        // 更新版本号
        for (const [key, version] of result.newVersions) {
          const record = this.cache.get(key);
          if (record) {
            record.meta.version = version;
            this.baseCache.set(key, cloneDeep(record));
          }
        }

        this._status = 'idle';
      } else if (result.conflicts.length > 0) {
        // 处理冲突：重新加载冲突的配置
        await this.resolveConflicts(result.conflicts);
        this._status = 'idle';
      } else if (result.error) {
        console.warn('[ConfigSync] Sync failed:', result.error);
        if (this.isRecoverableSyncError(result.error)) {
          this.enqueueOfflineChanges(mergedChanges);
          this._status = 'offline';
        } else {
          this._status = 'error';
        }
      }

      return result;
    } catch (error) {
      // 网络错误：保存到离线队列
      if (this.isNetworkError(error)) {
        console.warn('[ConfigSync] Network error, saving to offline queue');
        this.enqueueOfflineChanges(mergedChanges);
        this._status = 'offline';
        return {
          success: false,
          conflicts: [],
          newVersions: new Map(),
          error: 'Network error, changes saved to offline queue',
        };
      }

      console.warn('[ConfigSync] Sync failed:', error);
      this._status = 'error';
      throw error;
    }
  }

  /**
   * 合并变更：同一 key 取最新 value。
   * expectedVersion 始终取自 baseCache（即最新确认的服务端版本），以避免本地连续更新造成的版本号自我冲突。
   */
  private mergeChanges(changes: ConfigChange[]): ConfigChange[] {
    const latestByKey = new Map<ConfigKey, ConfigChange>();
    for (const change of changes) {
      latestByKey.set(change.key, change);
    }
    return Array.from(latestByKey.entries()).map(([key, latest]) => {
      const expectedVersion = this.baseCache.get(key)?.meta.version ?? latest.expectedVersion;
      return { ...latest, expectedVersion };
    });
  }

  /**
   * 解决冲突：以本地缓存为准，用服务端版本号重新同步。
   * 本地缓存始终是用户最新操作的结果，冲突仅因版本号不匹配，不应丢弃本地数据。
   */
  private async resolveConflicts(conflictKeys: ConfigKey[]): Promise<void> {
    const retryChanges: ConfigChange[] = [];

    for (const key of conflictKeys) {
      try {
        const serverRecord = await this.adapter.get(key);
        const localRecord = this.cache.get(key);
        const baseRecord = this.baseCache.get(key);

        if (serverRecord && localRecord) {
          const sameDevice =
            serverRecord.meta.deviceId === (this.adapter as BaseConfigAdapter).getDeviceId();
          const mergeBase = (baseRecord?.value ?? serverRecord.value) as Record<string, unknown>;

          const mergeResult = threeWayMerge(
            mergeBase,
            localRecord.value as Record<string, unknown>,
            serverRecord.value as Record<string, unknown>,
          );
          if (!mergeResult.hasConflict) {
            // 自动合并成功，静默处理
            localRecord.value = mergeResult.merged as ConfigValueMap[typeof key];
            localRecord.meta.version = serverRecord.meta.version;
            this.baseCache.set(key, cloneDeep(serverRecord)); // 更新 baseCache 为服务端版本
            retryChanges.push({
              key,
              value: localRecord.value,
              expectedVersion: serverRecord.meta.version,
              timestamp: Date.now(),
            });
            // 通知 UI 更新合并后的值
            this.notifyListeners(key, localRecord.value as ConfigValueMap[typeof key], localRecord.meta);
            continue;
          }

          // 同浏览器 profile 冲突：静默保留本地，不打扰用户
          let keepLocal = sameDevice;
          if (!keepLocal) {
            keepLocal = this.conflictResolver
              ? await Promise.resolve(
                  this.conflictResolver({
                    configKey: key,
                    localVersion: localRecord.meta.version,
                    serverVersion: serverRecord.meta.version,
                    deviceId: serverRecord.meta.deviceId,
                    localValue: localRecord.value,
                    serverValue: serverRecord.value,
                  }),
                ).catch((error: unknown) => {
                  console.warn(`[ConfigSync] Conflict resolver failed for '${key}':`, error);
                  return true;
                })
              : true;
          }

          if (keepLocal !== false) {
            // 用服务端版本号更新本地元数据，保留本地值并重新同步
            localRecord.meta.version = serverRecord.meta.version;
            this.baseCache.set(key, cloneDeep(serverRecord)); // 更新 baseCache
            retryChanges.push({
              key,
              value: localRecord.value,
              expectedVersion: serverRecord.meta.version,
              timestamp: Date.now(),
            });
          } else {
            // 采用服务端版本覆盖本地缓存
            this.cache.set(key, serverRecord as ConfigRecord);
            this.baseCache.set(key, cloneDeep(serverRecord)); // 更新 baseCache
            this.notifyListeners(key, serverRecord.value as ConfigValueMap[typeof key], serverRecord.meta);
          }
        } else if (serverRecord) {
          this.cache.set(key, serverRecord as ConfigRecord);
          this.baseCache.set(key, cloneDeep(serverRecord));
          this.notifyListeners(key, serverRecord.value as ConfigValueMap[typeof key], serverRecord.meta);
        }
      } catch (error) {
        console.warn(`[ConfigSync] Failed to resolve conflict for '${key}':`, error);
      }
    }

    // 用正确的版本号重新同步本地数据
    if (retryChanges.length > 0) {
      try {
        const result = await this.adapter.sync(retryChanges);
        if (result.success) {
          for (const [key, version] of result.newVersions) {
            const record = this.cache.get(key);
            if (record) {
              record.meta.version = version;
              // 更新 baseCache 的版本号
              const baseRec = this.baseCache.get(key);
              if (baseRec) baseRec.meta.version = version;
            }
          }
        } else {
          // 重试失败，放回队列，等待下次防抖同步，保护本地数据不被服务端覆盖
          console.warn('[ConfigSync] Conflict retry failed, saving to offline queue');
          this.changeQueue.push(...retryChanges);
          this.saveOfflineQueue(retryChanges);
          this.scheduleSyncDebounced();
        }
      } catch (error) {
        // 网络异常，放回队列
        console.warn('[ConfigSync] Conflict retry error, saving to offline queue:', error);
        this.changeQueue.push(...retryChanges);
        this.saveOfflineQueue(retryChanges);
        this.scheduleSyncDebounced();
      }
    }
  }

  /**
   * 通知监听器
   */
  private notifyListeners<K extends ConfigKey>(key: K, value: ConfigValueMap[K], meta: ConfigRecord<K>['meta']): void {
    if (shouldSuppressE2eSearchInbound(key)) {
      return;
    }
    const listeners = this.listeners.get(key);
    if (listeners) {
      for (const listener of listeners) {
        try {
          listener(key, value, meta);
        } catch (error) {
          console.warn(`[ConfigSync] Listener error for '${key}':`, error);
        }
      }
    }
  }

  /**
   * 判断是否为网络错误
   */
  private isNetworkError(error: unknown): boolean {
    return error instanceof TypeError && (error.message.includes('fetch') || error.message.includes('network'));
  }

  private isRecoverableSyncError(error: string): boolean {
    const normalized = error.toLowerCase();
    return (
      normalized.includes('backend not available') || normalized.includes('network') || normalized.includes('offline')
    );
  }

  private enqueueOfflineChanges(changes: ConfigChange[]): void {
    if (changes.length === 0) return;
    this.changeQueue.push(...changes);
    this.saveOfflineQueue(changes);
    this.scheduleSyncDebounced();
  }

  private registerOnlineHandler(): void {
    if (typeof window === 'undefined' || this.onlineHandlerRegistered) return;
    this.onlineHandlerRegistered = true;
    window.addEventListener('online', () => {
      void this.retryOfflineQueue();
    });
  }

  private async retryOfflineQueue(): Promise<void> {
    const pending = this.loadOfflineQueue();
    if (pending.length > 0) {
      this.changeQueue.push(...pending);
      this.clearOfflineQueue();
    }
    if (this.changeQueue.length > 0) {
      await this.flushSync();
    }
  }

  // ============================================================================
  // 离线队列管理
  // ============================================================================

  /**
   * 加载离线队列
   */
  private loadOfflineQueue(): ConfigChange[] {
    if (typeof window === 'undefined') return [];

    try {
      const stored = localStorage.getItem(OFFLINE_QUEUE_KEY);
      if (!stored) return [];
      return JSON.parse(stored) as ConfigChange[];
    } catch {
      return [];
    }
  }

  /**
   * 保存离线队列
   */
  private saveOfflineQueue(changes: ConfigChange[]): void {
    if (typeof window === 'undefined') return;

    try {
      // 合并现有队列和新变更
      const existing = this.loadOfflineQueue();
      const merged = this.mergeChanges([...existing, ...changes]);
      localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(merged));
    } catch (error) {
      console.warn('[ConfigSync] Failed to save offline queue:', error);
    }
  }

  /**
   * 清空离线队列
   */
  private clearOfflineQueue(): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem(OFFLINE_QUEUE_KEY);
  }
}

// 全局单例
let _instance: ConfigSyncManager | null = null;

/**
 * 获取配置同步管理器单例
 */
export function getConfigSyncManager(): ConfigSyncManager {
  if (
    !_instance ||
    typeof (
      _instance as ConfigSyncManager & {
        setConflictResolver?: unknown;
      }
    ).setConflictResolver !== 'function'
  ) {
    _instance = new ConfigSyncManager();
  }
  return _instance;
}

/**
 * 重置配置同步管理器（仅用于测试）
 */
export function resetConfigSyncManager(): void {
  _instance = null;
}

export { ConfigSyncManager };
