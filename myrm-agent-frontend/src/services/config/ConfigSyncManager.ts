/**
 * 配置同步管理器
 *
 * 统一管理配置的加载、缓存、同步。
 *
 * 核心特性：
 * - 乐观更新：先更新 UI，再异步同步
 * - 写入出口（防抖、离线队列、重放、联网重试）由 `outbox.ts` 承担；只有白名单内的非敏感键落盘（`offlineQueue.ts`）
 * - 主题 fast-path：personalSettings 主题字段变更立即 flush + offline queue 落盘
 * - 冲突检测：版本号乐观锁；冲突分级消解见 `conflictResolution.ts`，离线重放的过期闸门见 `offlineReplay.ts`
 */

import { ensureLocalBackendReady } from '@/lib/backend-health';
import { isLocalMode } from '@/lib/deploy-mode';
import { ensurePlatformReadiness } from '@/lib/platform-readiness';
import { cloneDeep } from 'lodash-es';
import { valuesEqual } from './configFingerprint';
import { ConfigListenerRegistry } from './configListeners';
import type { ConfigChangeListener } from './configListeners';
import type { ConfigConflictResolver, RecordSink } from './conflictResolution';
import { isE2eBlockedKey } from './e2eSearchSyncGate';
import { landLateRecords, loadInitialConfigs } from './initialLoad';
import { buildLocalRecord } from './localWrites';
import { ConfigOutbox } from './outbox';
import { reloadKeysFromServer } from './serverReload';
import { runStartupNormalization } from './startupNormalization';
import { isThemePersonalSettingsChange } from './themePersonalSettingsSync';
import { BaseConfigAdapter, TauriConfigAdapter, SandboxConfigAdapter } from './adapters';
import type { ConfigAdapter, ConfigKey, ConfigRecord, ConfigValueMap, SyncResult, SyncStatus } from './types';
import { createInitialVersion, incrementVersion } from './types';

export type { ConfigChangeListener } from './configListeners';
export type { ConfigConflictResolution, ConfigConflictResolver } from './conflictResolution';

/** 配置同步管理器 */
class ConfigSyncManager {
  private adapter: ConfigAdapter;
  private cache: Map<ConfigKey, ConfigRecord> = new Map();
  private baseCache: Map<ConfigKey, ConfigRecord> = new Map();
  private listeners = new ConfigListenerRegistry();
  private conflictResolver: ConfigConflictResolver | null = null;
  private _status: SyncStatus = 'idle';
  private _isInitialized = false;
  private _initializingPromise: Promise<Map<ConfigKey, ConfigRecord>> | null = null;
  private readonly outbox = new ConfigOutbox({
    context: () => ({
      ...this.recordSink(),
      adapter: this.adapter,
      deviceId: this.deviceId,
      resolver: this.conflictResolver,
    }),
    ensureKeyLoaded: (key) => this.ensureKeyLoaded(key),
    initialize: () => this.initialize(),
    isInitialized: () => this._isInitialized,
    setStatus: (status) => {
      this._status = status;
    },
  });

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
      // 先于后端可达性检查：含密钥的条目不能在后端不可达期间继续明文留在浏览器存储里，
      // 无从归属账号的积压也不该留到联网后被重放。
      this.outbox.prepareStoredQueue();

      if (isLocalMode()) {
        const ready = await ensureLocalBackendReady();
        if (!ready) {
          this._status = 'offline';
          this.outbox.registerOnlineHandler();
          void ensurePlatformReadiness().then((snapshot) => {
            if (snapshot.database && !this._isInitialized) {
              void this.initialize();
            }
          });
          return this.cache;
        }
      }

      const offlineChanges = this.outbox.collectOfflineChanges();
      const coreFirst = !isLocalMode() && this.adapter instanceof SandboxConfigAdapter;

      const { configs, loadRemaining } = await loadInitialConfigs(this.adapter, coreFirst);
      this.cache = configs;
      this.baseCache = cloneDeep(configs);
      this._isInitialized = true;
      this._status = 'idle';

      loadRemaining?.().then(
        (rest) => this.landLate(rest),
        (err) => {
          console.warn('[ConfigSync] Background preload failed:', err);
        },
      );

      await this.outbox.replayOfflineChanges(offlineChanges);
      this.outbox.registerOnlineHandler();

      return this.cache;
    } catch (error) {
      console.warn('[ConfigSync] Initialization failed, entering offline mode for retry:', error);
      this._status = 'offline';
      this.outbox.registerOnlineHandler();
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
   * 渐进加载模式下 initialize() 只保证核心 key 就绪，其余 key 后台异步预加载；对「读取即决策」的路径
   * （如 YOLO 互斥、搜索服务检查）必须显式等待目标 key，否则读到 null/旧值会把「没取到」当成「没有」，互斥静默跳过（安全假象）。
   * 返回 true：状态已知（缓存命中，或服务端已答复，含「没有这一行」）；false：请求失败、状态未知。永不抛出。
   */
  async ensureKeyLoaded<K extends ConfigKey>(key: K): Promise<boolean> {
    await this.initialize();
    if (this.cache.has(key)) {
      return true;
    }
    try {
      const record = await this.adapter.get(key);
      if (record) {
        this.landLate([[key, record as ConfigRecord]]);
      }
      return true;
    } catch (error) {
      console.warn(`[ConfigSync] ensureKeyLoaded failed for '${key}':`, error);
      return false;
    }
  }

  /** 后端在页面存活期间改了这些配置行时，换上后端的当前值（本地尚未同步的改动保留，见 `serverReload.ts`）。 */
  async reloadKeys(keys: readonly ConfigKey[]): Promise<void> {
    await this.initialize();
    await reloadKeysFromServer({ ...this.recordSink(), adapter: this.adapter }, keys);
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
    const newRecord = buildLocalRecord(key, value, incrementVersion(currentVersion), this.deviceId);
    this.cache.set(key, newRecord as ConfigRecord);

    // 2. 通知监听器
    this.notifyListeners(key, value, newRecord.meta);

    // E2E 隔离：搜索配置只改本地缓存，不进入同步队列
    if (isE2eBlockedKey(key)) {
      this.outbox.dropBlockedChanges();
      return;
    }

    // 3. 记录待同步变更。安全关键路径 fast-path：securityConfig 立即 flush（YOLO 关闭等安全变更
    //    不应受 1s debounce 影响——否则用户操作后立刻关闭/刷新页面会丢失变更，
    //    造成「UI 显示已关闭但后端仍开启」的安全假象）；其余走防抖同步。
    const immediate =
      key === 'securityConfig' ||
      (key === 'personalSettings' &&
        isThemePersonalSettingsChange(
          current?.value as ConfigValueMap['personalSettings'] | undefined,
          value as ConfigValueMap['personalSettings'],
        ));
    this.outbox.enqueue({ key, value, expectedVersion: currentVersion, timestamp: Date.now() }, immediate);
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
  forceSync(): Promise<SyncResult> {
    return this.outbox.forceSync();
  }

  /** 释放定时器与联网监听（单例被重置或替换时调用）。 */
  dispose(): void {
    this.outbox.dispose();
  }

  /** 本机写入的记录以它作为作者。 */
  private get deviceId(): string {
    return (this.adapter as BaseConfigAdapter).getDeviceId();
  }

  /** 读取时才取 cache：`initialize()` 会整体替换两张缓存表。 */
  private recordSink(): RecordSink {
    return { cache: this.cache, baseCache: this.baseCache, notify: this.notifyListeners.bind(this) };
  }

  /** 首屏之后才到的记录（后台预加载、按需读取单个 key）统一从这里落进缓存空缺；缓存已有的 key 不被迟到的答复覆盖。 */
  private landLate(records: Iterable<[ConfigKey, ConfigRecord]>): void {
    landLateRecords(records, this.recordSink());
  }

  /** 通知监听器 */
  private notifyListeners<K extends ConfigKey>(key: K, value: ConfigValueMap[K], meta: ConfigRecord<K>['meta']): void {
    if (isE2eBlockedKey(key)) {
      return;
    }
    this.listeners.notify(key, value, meta);
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
  _instance?.dispose();
  _instance = null;
}

export { ConfigSyncManager };
