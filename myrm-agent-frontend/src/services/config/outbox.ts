/**
 * [INPUT]
 * - `./conflictResolution` resolveConflicts / ConflictContext (POS: conflict tiers; the live caches and the adapter are handed in)
 * - `./e2eSearchSyncGate` withoutBlockedSearchChanges (POS: E2E switch that keeps the search config local)
 * - `./localWrites` applyReplayedChanges / recordSyncedChanges (POS: cache bookkeeping of writes made on this device)
 * - `./offlineQueue` loadOfflineQueue / saveOfflineQueue / clearOfflineQueue / takeUnpersistableOfflineEntries (POS: browser-storage half of the offline queue)
 * - `./offlineReplay` mergeLatestChanges / partitionOfflineChanges (POS: one change per key, replay staleness gate)
 * - `./types` ConfigChange / SyncResult / SyncStatus (POS: queued write, backend answer, manager state)
 *
 * [OUTPUT]
 * ConfigOutbox: the write path of the config sync layer: queue, debounce, send, offline retention and replay.
 * OutboxHost: what the outbox reads from the manager that owns it.
 *
 * [POS]
 * Everything between `ConfigSyncManager.set()` and the backend. The manager keeps the caches and the read path; the
 * outbox owns the pending changes and the timers and listeners that move them, so `dispose()` can release them all.
 * The host is read at call time because the manager replaces its cache tables when it (re)initialises.
 */
import { resolveConflicts } from './conflictResolution';
import type { ConflictContext } from './conflictResolution';
import { withoutBlockedSearchChanges } from './e2eSearchSyncGate';
import { applyReplayedChanges, recordSyncedChanges } from './localWrites';
import {
  clearOfflineQueue,
  isRecoverableSyncError,
  loadOfflineQueue,
  saveOfflineQueue,
  takeUnpersistableOfflineEntries,
} from './offlineQueue';
import { mergeLatestChanges, partitionOfflineChanges } from './offlineReplay';
import type { ConfigChange, ConfigKey, SyncResult, SyncStatus } from './types';

// 防抖延迟（毫秒）
const SYNC_DEBOUNCE_MS = 1000;

export interface OutboxHost {
  context(): Omit<ConflictContext, 'requeue'>;
  ensureKeyLoaded(key: ConfigKey): Promise<boolean>;
  initialize(): Promise<unknown>;
  isInitialized(): boolean;
  setStatus(status: SyncStatus): void;
}

export class ConfigOutbox {
  private changeQueue: ConfigChange[] = [];
  /** 非白名单键的待重放变更：不允许留在浏览器存储里，只在内存里等待重放。 */
  private memoryOnlyOfflineChanges: ConfigChange[] = [];
  private syncDebounceTimer: ReturnType<typeof setTimeout> | null = null;
  private onlineHandlerRegistered = false;
  private readonly handleOnline = (): void => {
    void this.retryOfflineQueue();
  };

  constructor(private readonly host: OutboxHost) {}

  /** `immediate` 跳过防抖并先把队列落盘：安全关键写入不能被「用户操作后立刻关闭页面」丢掉。 */
  enqueue(change: ConfigChange, immediate: boolean): void {
    this.changeQueue.push(change);
    if (immediate) {
      saveOfflineQueue(this.changeQueue);
      this.cancelScheduledSync();
      void this.flushSync();
      return;
    }
    this.scheduleSyncDebounced();
  }

  dropBlockedChanges(): void {
    this.changeQueue = withoutBlockedSearchChanges(this.changeQueue);
  }

  /** 强制立即同步 */
  async forceSync(): Promise<SyncResult> {
    this.cancelScheduledSync();
    return this.flushSync();
  }

  /** 含密钥的条目不能在后端不可达期间继续明文留在浏览器存储里：先移进内存。 */
  liftUnpersistableEntries(): void {
    this.memoryOnlyOfflineChanges.push(...takeUnpersistableOfflineEntries());
  }

  /** 待重放的离线变更：内存里的非白名单条目 + 浏览器存储里的白名单条目。 */
  collectOfflineChanges(): ConfigChange[] {
    return [...this.memoryOnlyOfflineChanges, ...loadOfflineQueue()];
  }

  /** 服务端已前进的过期条目被丢弃（服务端值胜出）；其余乐观写入缓存后带着原基准版本同步。 */
  async replayOfflineChanges(pending: ConfigChange[]): Promise<void> {
    if (pending.length === 0) {
      return;
    }
    console.warn(`[ConfigSync] Found ${pending.length} offline changes, syncing...`);
    // 渐进加载下缓存只含核心键：队列里的非核心键没补载入就比对，会把「没取到」当成「服务端已前进」。
    await Promise.all(pending.map((change) => this.host.ensureKeyLoaded(change.key)));
    const { cache, resolver } = this.host.context();
    const replayable = await partitionOfflineChanges(pending, cache, resolver);
    this.memoryOnlyOfflineChanges = [];
    clearOfflineQueue();
    if (replayable.length > 0) {
      const sink = this.host.context();
      applyReplayedChanges(sink, sink.deviceId, replayable);
      this.changeQueue = replayable;
      await this.flushSync({ preserveExpectedVersion: true });
    }
  }

  registerOnlineHandler(): void {
    if (typeof window === 'undefined' || this.onlineHandlerRegistered) {
      return;
    }
    this.onlineHandlerRegistered = true;
    window.addEventListener('online', this.handleOnline);
  }

  /** 释放定时器与联网监听；未发出的变更随实例丢弃。 */
  dispose(): void {
    this.cancelScheduledSync();
    if (typeof window !== 'undefined') {
      window.removeEventListener('online', this.handleOnline);
    }
    this.onlineHandlerRegistered = false;
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

    const { adapter, baseCache } = this.host.context();
    // 合并同一 key 的连续变更，取最后一个
    const mergedChanges = mergeLatestChanges(this.changeQueue, baseCache, options?.preserveExpectedVersion === true);
    this.changeQueue = [];

    this.host.setStatus('syncing');

    try {
      const result = await adapter.sync(mergedChanges);

      if (result.success) {
        // 清空离线队列
        clearOfflineQueue();

        const sink = this.host.context();
        recordSyncedChanges(sink, sink.deviceId, mergedChanges, result.newVersions);

        this.host.setStatus('idle');
      } else if (result.conflicts.length > 0) {
        // 处理冲突：重新加载冲突的配置
        await resolveConflicts(this.conflictContext(), result.conflicts);
        this.host.setStatus('idle');
      } else if (result.error) {
        console.warn('[ConfigSync] Sync failed:', result.error);
        if (isRecoverableSyncError(result.error)) {
          this.enqueueOfflineChanges(mergedChanges);
          this.host.setStatus('offline');
        } else {
          this.host.setStatus('error');
        }
      }

      return result;
    } catch (error) {
      // 适配器把传输失败折算成失败结果（见 `adapters/_ARCH.md`），走到这里的是后端明确拒绝的写入。
      console.warn('[ConfigSync] Sync failed:', error);
      this.host.setStatus('error');
      throw error;
    }
  }

  private conflictContext(): ConflictContext {
    return { ...this.host.context(), requeue: (changes) => this.enqueueOfflineChanges(changes) };
  }

  private enqueueOfflineChanges(changes: ConfigChange[]): void {
    if (changes.length === 0) {
      return;
    }
    this.changeQueue.push(...changes);
    saveOfflineQueue(changes);
    this.scheduleSyncDebounced();
  }

  private async retryOfflineQueue(): Promise<void> {
    // 启动失败时服务端状态从未载入：先重新初始化（它自己会载入并重放队列），仍不可达就留在队列里等下一次联网。
    await this.host.initialize();
    if (!this.host.isInitialized()) {
      return;
    }
    await this.replayOfflineChanges(this.collectOfflineChanges());
    if (this.changeQueue.length > 0) {
      await this.flushSync();
    }
  }
}
