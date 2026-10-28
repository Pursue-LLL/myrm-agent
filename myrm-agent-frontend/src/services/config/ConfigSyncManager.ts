/**
 * 配置同步管理器
 *
 * 统一管理配置的加载、缓存、同步。
 *
 * 核心特性：
 * - 乐观更新：先更新 UI，再异步同步
 * - 防抖同步：避免频繁写入
 * - 主题 fast-path：personalSettings 主题字段变更立即 flush + offline queue 落盘
 * - 离线支持：网络不可用时保存到本地队列；只有白名单内的非敏感键落盘，其余键只在内存里重试（`offlineQueue.ts`）
 * - 冲突检测：版本号乐观锁；冲突分级消解见 `conflictResolution.ts`，离线重放的过期闸门见 `offlineReplay.ts`
 */

import { ensureLocalBackendReady } from '@/lib/backend-health';
import { isLocalMode } from '@/lib/deploy-mode';
import { ensurePlatformReadiness } from '@/lib/platform-readiness';
import { cloneDeep } from 'lodash-es';
import { valuesEqual } from './configFingerprint';
import { ConfigListenerRegistry } from './configListeners';
import type { ConfigChangeListener } from './configListeners';
import { resolveConflicts } from './conflictResolution';
import type { ConflictContext, ConfigConflictResolver } from './conflictResolution';
import { isE2eBlockedKey, withoutBlockedSearchChanges } from './e2eSearchSyncGate';
import { loadInitialConfigs } from './initialLoad';
import {
  clearOfflineQueue,
  isNetworkError,
  isRecoverableSyncError,
  loadOfflineQueue,
  saveOfflineQueue,
  takeUnpersistableOfflineEntries,
} from './offlineQueue';
import { mergeLatestChanges, partitionOfflineChanges } from './offlineReplay';
import { runStartupNormalization } from './startupNormalization';
import { isThemePersonalSettingsChange } from './themePersonalSettingsSync';
import { BaseConfigAdapter, TauriConfigAdapter, SandboxConfigAdapter } from './adapters';
import type { ConfigAdapter, ConfigKey, ConfigRecord, ConfigChange, ConfigValueMap, SyncResult } from './types';
import { createInitialVersion, incrementVersion } from './types';

export type { ConfigChangeListener } from './configListeners';
export type { ConfigConflictResolution, ConfigConflictResolver } from './conflictResolution';

// 防抖延迟（毫秒）
const SYNC_DEBOUNCE_MS = 1000;

/** 同步状态 */
export type SyncStatus = 'idle' | 'loading' | 'syncing' | 'error' | 'offline';

/** 配置同步管理器 */
class ConfigSyncManager {
  private adapter: ConfigAdapter;
  private cache: Map<ConfigKey, ConfigRecord> = new Map();
  private baseCache: Map<ConfigKey, ConfigRecord> = new Map();
  private changeQueue: ConfigChange[] = [];
  /** 非白名单键的待重放变更：不允许留在浏览器存储里，只在内存里等待重放。 */
  private memoryOnlyOfflineChanges: ConfigChange[] = [];
  private syncDebounceTimer: ReturnType<typeof setTimeout> | null = null;
  private listeners = new ConfigListenerRegistry();
  private conflictResolver: ConfigConflictResolver | null = null;
  private _status: SyncStatus = 'idle';
  private _isInitialized = false;
  private _initializingPromise: Promise<Map<ConfigKey, ConfigRecord>> | null = null;
  private onlineHandlerRegistered = false;

  constructor() {
    this.adapter = isLocalMode() ? new TauriConfigAdapter() : new SandboxConfigAdapter();
  }

  /** 获取当前同步状态 */
  get status(): SyncStatus {
    return this._status;
  }

  /** 是否已初始化 */
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
    if (this._initializingPromise) {
      return this._initializingPromise;
    }

    this._initializingPromise = this._doInitialize();
    try {
      return await this._initializingPromise;
    } finally {
      this._initializingPromise = null;
    }
  }

  private async _doInitialize(): Promise<Map<ConfigKey, ConfigRecord>> {
    this._status = 'loading';

    try {
      // 先于后端可达性检查：含密钥的条目不能在后端不可达期间继续明文留在浏览器存储里。
      this.memoryOnlyOfflineChanges.push(...takeUnpersistableOfflineEntries());

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

      const offlineChanges = this.collectOfflineChanges();
      const coreFirst = !isLocalMode() && this.adapter instanceof SandboxConfigAdapter;

      const { configs, loadRemaining } = await loadInitialConfigs(this.adapter, coreFirst);
      this.cache = configs;
      this.baseCache = cloneDeep(configs);
      this._isInitialized = true;
      this._status = 'idle';

      loadRemaining?.().then(
        (rest) => {
          for (const [k, v] of rest) {
            this.cache.set(k, v);
            this.baseCache.set(k, cloneDeep(v));
            // 通知订阅者：预加载写入不进 set()，不通知则依赖「配置就绪」的兜底逻辑
            // （如 securityConfig ⇄ YOLO 互斥重放）永远收不到触发。
            this.notifyListeners(k, v.value as ConfigValueMap[ConfigKey], v.meta);
          }
        },
        (err) => {
          console.warn('[ConfigSync] Background preload failed:', err);
        },
      );

      await this.replayOfflineChanges(offlineChanges);
      this.registerOnlineHandler();

      return this.cache;
    } catch (error) {
      console.warn('[ConfigSync] Initialization failed, entering offline mode for retry:', error);
      this._status = 'offline';
      this.registerOnlineHandler();
      return this.cache;
    }
  }

  /** 获取配置（优先缓存） */
  get<K extends ConfigKey>(key: K): ConfigValueMap[K] | null {
    const record = this.cache.get(key) as ConfigRecord<K> | undefined;
    return record?.value ?? null;
  }

  /**
   * 确保目标 key 已同步到本地缓存后再返回。
   * 渐进加载模式下 initialize() 只保证核心 key 就绪，其余 key 后台异步预加载；
   * 对「读取即决策」的安全敏感路径（如 YOLO 互斥）必须显式等待目标 key，
   * 否则可能读到 null/旧值导致互斥静默跳过（安全假象）。
   */
  async ensureKeyLoaded<K extends ConfigKey>(key: K): Promise<void> {
    await this.initialize();
    if (this.cache.has(key)) {
      return;
    }
    try {
      const record = await this.adapter.get(key);
      if (record) {
        this.cache.set(key, record as ConfigRecord);
        this.baseCache.set(key, cloneDeep(record));
        this.notifyListeners(key, record.value as ConfigValueMap[K], record.meta);
      }
    } catch (error) {
      console.warn(`[ConfigSync] ensureKeyLoaded failed for '${key}':`, error);
    }
  }

  /** 已加密存储但密钥丢失、读不出内容的配置键（用户显式保存后即不再列出）。 */
  getUnreadableKeys(): ConfigKey[] {
    return [...this.cache.values()].filter((record) => record.unreadable).map((record) => record.key);
  }

  /** 获取配置记录（包含元数据） */
  getRecord<K extends ConfigKey>(key: K): ConfigRecord<K> | null {
    return (this.cache.get(key) as ConfigRecord<K>) ?? null;
  }

  /** 设置冲突解决器 */
  setConflictResolver(resolver: ConfigConflictResolver | null): void {
    this.conflictResolver = resolver;
  }

  /**
   * 仅当内容与 baseCache 不同时才写入并同步。
   * 用于启动迁移，避免无意义的版本 bump 和冲突。
   */
  commitIfDirty<K extends ConfigKey>(key: K, value: ConfigValueMap[K]): boolean {
    const base = this.baseCache.get(key);
    if (base?.unreadable) {
      // 服务端已有加密数据但打不开：空值不是「用户没配置」，自动回写默认值会覆盖它，只能等用户显式保存。
      return false;
    }
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
    await runStartupNormalization(this.cache, this.baseCache, (key, value) => this.commitIfDirty(key, value));
  }

  /** 设置配置（乐观更新 + 异步同步） */
  set<K extends ConfigKey>(key: K, value: ConfigValueMap[K]): void {
    const current = this.cache.get(key) as ConfigRecord<K> | undefined;
    const currentVersion = current?.meta.version ?? createInitialVersion();

    // 1. 乐观更新缓存
    const newRecord = this.buildRecord(key, value, incrementVersion(currentVersion));
    this.cache.set(key, newRecord as ConfigRecord);

    // 2. 通知监听器
    this.notifyListeners(key, value, newRecord.meta);

    // E2E 隔离：搜索配置只改本地缓存，不进入同步队列
    if (isE2eBlockedKey(key)) {
      this.changeQueue = withoutBlockedSearchChanges(this.changeQueue);
      return;
    }

    // 3. 记录待同步变更
    this.changeQueue.push({
      key,
      value,
      expectedVersion: currentVersion,
      timestamp: Date.now(),
    });

    // 4. 安全关键路径 fast-path：securityConfig 立即 flush（YOLO 关闭等安全变更
    //    不应受 1s debounce 影响——否则用户操作后立刻关闭/刷新页面会丢失变更，
    //    造成「UI 显示已关闭但后端仍开启」的安全假象）。
    if (
      key === 'securityConfig' ||
      (key === 'personalSettings' &&
        isThemePersonalSettingsChange(
          current?.value as ConfigValueMap['personalSettings'] | undefined,
          value as ConfigValueMap['personalSettings'],
        ))
    ) {
      saveOfflineQueue(this.changeQueue);
      this.cancelScheduledSync();
      void this.flushSync();
      return;
    }

    // 5. 防抖同步
    this.scheduleSyncDebounced();
  }

  /** 删除配置 */
  async delete(key: ConfigKey): Promise<boolean> {
    const success = await this.adapter.delete(key);
    if (success) {
      this.cache.delete(key);
      this.baseCache.delete(key);
    }
    return success;
  }

  /** 订阅配置变更 */
  subscribe<K extends ConfigKey>(key: K, listener: ConfigChangeListener<K>): () => void {
    return this.listeners.subscribe(key, listener);
  }

  /** 强制立即同步 */
  async forceSync(): Promise<SyncResult> {
    this.cancelScheduledSync();
    return this.flushSync();
  }

  /** 防抖同步 */
  private scheduleSyncDebounced(): void {
    this.cancelScheduledSync();
    this.syncDebounceTimer = setTimeout(() => {
      this.flushSync();
    }, SYNC_DEBOUNCE_MS);
  }

  private cancelScheduledSync(): void {
    if (this.syncDebounceTimer) {
      clearTimeout(this.syncDebounceTimer);
      this.syncDebounceTimer = null;
    }
  }

  /** 立即同步所有待处理变更 */
  private async flushSync(options?: { preserveExpectedVersion?: boolean }): Promise<SyncResult> {
    this.changeQueue = withoutBlockedSearchChanges(this.changeQueue);
    if (this.changeQueue.length === 0) {
      return {
        success: true,
        conflicts: [],
        newVersions: new Map(),
      };
    }

    // 合并同一 key 的连续变更，取最后一个
    const mergedChanges = mergeLatestChanges(
      this.changeQueue,
      this.baseCache,
      options?.preserveExpectedVersion === true,
    );
    this.changeQueue = [];

    this._status = 'syncing';

    try {
      const result = await this.adapter.sync(mergedChanges);

      if (result.success) {
        // 清空离线队列
        clearOfflineQueue();

        // 同步成功：cache/baseCache 必须与 mergedChanges 一致（offline replay 等路径可能未先乐观更新）
        for (const change of mergedChanges) {
          const fallbackVersion = this.cache.get(change.key)?.meta.version ?? createInitialVersion();
          const newRecord = this.buildRecord(
            change.key,
            change.value,
            result.newVersions.get(change.key) ?? incrementVersion(fallbackVersion),
          );
          this.cache.set(change.key, newRecord);
          this.baseCache.set(change.key, cloneDeep(newRecord));
        }

        this._status = 'idle';
      } else if (result.conflicts.length > 0) {
        // 处理冲突：重新加载冲突的配置
        await resolveConflicts(this.conflictContext(), result.conflicts);
        this._status = 'idle';
      } else if (result.error) {
        console.warn('[ConfigSync] Sync failed:', result.error);
        if (isRecoverableSyncError(result.error)) {
          this.enqueueOfflineChanges(mergedChanges);
          this._status = 'offline';
        } else {
          this._status = 'error';
        }
      }

      return result;
    } catch (error) {
      // 网络错误：保存到离线队列
      if (isNetworkError(error)) {
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

  /** 与 set() 的乐观写入同语义：新记录不带 `unreadable`，用户显式保存即解除「读不出」标记。 */
  private buildRecord<K extends ConfigKey>(key: K, value: ConfigValueMap[K], version: string): ConfigRecord<K> {
    return {
      key,
      value,
      meta: {
        version,
        updatedAt: new Date().toISOString(),
        deviceId: (this.adapter as BaseConfigAdapter).getDeviceId(),
      },
    };
  }

  /** Apply queued change values to cache (mirrors set() optimistic write for offline replay). */
  private applyPendingChangesToCache(changes: ConfigChange[]): void {
    for (const change of mergeLatestChanges(changes, this.baseCache)) {
      const currentVersion = this.cache.get(change.key)?.meta.version ?? createInitialVersion();
      this.cache.set(change.key, this.buildRecord(change.key, change.value, incrementVersion(currentVersion)));
    }
  }

  private conflictContext(): ConflictContext {
    return {
      adapter: this.adapter,
      deviceId: (this.adapter as BaseConfigAdapter).getDeviceId(),
      cache: this.cache,
      baseCache: this.baseCache,
      resolver: this.conflictResolver,
      notify: (key, value, meta) => this.notifyListeners(key, value, meta),
      requeue: (changes) => this.enqueueOfflineChanges(changes),
    };
  }

  /** 通知监听器 */
  private notifyListeners<K extends ConfigKey>(key: K, value: ConfigValueMap[K], meta: ConfigRecord<K>['meta']): void {
    if (isE2eBlockedKey(key)) {
      return;
    }
    this.listeners.notify(key, value, meta);
  }

  private enqueueOfflineChanges(changes: ConfigChange[]): void {
    if (changes.length === 0) {
      return;
    }
    this.changeQueue.push(...changes);
    saveOfflineQueue(changes);
    this.scheduleSyncDebounced();
  }

  private registerOnlineHandler(): void {
    if (typeof window === 'undefined' || this.onlineHandlerRegistered) {
      return;
    }
    this.onlineHandlerRegistered = true;
    window.addEventListener('online', () => {
      void this.retryOfflineQueue();
    });
  }

  private async retryOfflineQueue(): Promise<void> {
    await this.replayOfflineChanges(this.collectOfflineChanges());
    if (this.changeQueue.length > 0) {
      await this.flushSync();
    }
  }

  /** 待重放的离线变更：内存里的非白名单条目 + 浏览器存储里的白名单条目。 */
  private collectOfflineChanges(): ConfigChange[] {
    return [...this.memoryOnlyOfflineChanges, ...loadOfflineQueue()];
  }

  /** 服务端已前进的过期条目被丢弃（服务端值胜出）；其余乐观写入缓存后带着原基准版本同步。 */
  private async replayOfflineChanges(pending: ConfigChange[]): Promise<void> {
    if (pending.length === 0) {
      return;
    }
    console.warn(`[ConfigSync] Found ${pending.length} offline changes, syncing...`);
    const replayable = await partitionOfflineChanges(pending, this.cache, this.conflictResolver);
    this.memoryOnlyOfflineChanges = [];
    clearOfflineQueue();
    if (replayable.length > 0) {
      this.applyPendingChangesToCache(replayable);
      this.changeQueue = replayable;
      await this.flushSync({ preserveExpectedVersion: true });
    }
  }
}

// 全局单例
let _instance: ConfigSyncManager | null = null;

/** 获取配置同步管理器单例 */
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

/** 重置配置同步管理器（仅用于测试） */
export function resetConfigSyncManager(): void {
  _instance = null;
}

export { ConfigSyncManager };
