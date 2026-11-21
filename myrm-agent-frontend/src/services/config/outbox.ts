/**
 * [INPUT]
 * - `./conflictResolution` resolveConflicts / ConflictContext (POS: conflict tiers; the live caches and the adapter are handed in)
 * - `./e2eSearchSyncGate` withoutBlockedSearchChanges (POS: E2E switch that keeps the search config local)
 * - `./localWrites` applyReplayedChanges / recordSyncedChanges (POS: cache bookkeeping of writes made on this device)
 * - `./offlineQueue` loadOfflineQueue / saveOfflineQueue / removeOfflineEntries / takeUnpersistableOfflineEntries / discardUnattributedOfflineQueue (POS: per-account browser-storage half of the offline queue)
 * - `./offlineReplay` mergeLatestChanges / decideReplay (POS: one change per key on the confirmed version, per-change replay decisions)
 * - `./outboxAnswer` mergeAnswers / partitionByAnswer (POS: how a backend answer maps onto the batch it answers)
 * - `./retryBackoff` RetryBackoff (POS: one pending retry whose pause doubles from 1 s up to a minute)
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
 *
 * One batch is in flight at a time, built after the previous answer is applied so it carries the version that answer
 * returned and never races it into a conflict. An answer settles only the keys it names: accepted keys are
 * acknowledged (merge base, cache, stored copy), clashing keys go to the resolver (newer edits of such a key wait for
 * the answer, other keys keep flowing), every other change stays queued.
 *
 * A change the backend did not take stays queued (and stored, for allowlisted keys) and is retried with backoff;
 * `forceSync()` reports it as a failed result. A batch the backend refuses outright is sent again key by key, so only
 * the refused keys lose their write; the refusal still rejects `forceSync()`. A change that will not be sent (refused,
 * answered with an application error, overruled by the server's value) takes its stored copy with it, or it would come
 * back at every start.
 *
 * Replay judges what a previous session left behind one change at a time (`decideReplay`): settled ones leave the
 * store, unreadable ones stay stored for the next replay, the rest join the queue ahead of newer edits and go out like
 * any write; a stored copy goes only after the backend has taken it.
 */
import { resolveConflicts } from './conflictResolution';
import type { ConflictContext } from './conflictResolution';
import { withoutBlockedSearchChanges } from './e2eSearchSyncGate';
import { applyReplayedChanges, recordSyncedChanges } from './localWrites';
import {
  discardUnattributedOfflineQueue,
  isRecoverableSyncError,
  loadOfflineQueue,
  removeOfflineEntries,
  saveOfflineQueue,
  takeUnpersistableOfflineEntries,
} from './offlineQueue';
import { decideReplay, mergeLatestChanges } from './offlineReplay';
import { mergeAnswers, partitionByAnswer } from './outboxAnswer';
import { RetryBackoff } from './retryBackoff';
import type { ConfigChange, ConfigKey, ConfigVersion, SyncResult, SyncStatus } from './types';

// 防抖延迟（毫秒）
const SYNC_DEBOUNCE_MS = 1000;

export interface OutboxHost {
  context(): ConflictContext;
  ensureKeyLoaded(key: ConfigKey): Promise<boolean>;
  initialize(): Promise<unknown>;
  isInitialized(): boolean;
  setStatus(status: SyncStatus): void;
}

/** One send: the backend's answer or its outright refusal, plus the settlement of the clashes it raised. */
type Delivery = { result: SyncResult; settled: Promise<void> } | { refusal: unknown; settled: Promise<void> };

const nothingSent = (): Delivery => ({ result: mergeAnswers([]), settled: Promise.resolve() });

export class ConfigOutbox {
  private queue: ConfigChange[] = [];
  /** 非白名单键的待重放变更：不允许留在浏览器存储里，只在内存里等待重放。 */
  private memoryOnlyOfflineChanges: ConfigChange[] = [];
  private syncDebounceTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly retry = new RetryBackoff(() => this.background(this.flush()));
  private onlineHandlerRegistered = false;
  /** The latest send in the chain: the next one starts when it ends. */
  private lastSend: Promise<unknown> = Promise.resolve();
  private lastEditTime = 0;
  /** Keys whose clash with the server is being settled: their newer edits stay queued until it is. */
  private readonly clashing = new Set<ConfigKey>();
  private readonly handleOnline = (): void => {
    this.background(this.retryOfflineQueue());
  };

  constructor(private readonly host: OutboxHost) {}

  /** `immediate` 跳过防抖并先把队列落盘：安全关键写入不能被「用户操作后立刻关闭页面」丢掉。 */
  enqueue(change: ConfigChange, immediate: boolean): void {
    this.queue.push(this.stamped(change));
    if (immediate) {
      saveOfflineQueue(this.queue);
      this.cancelScheduledSync();
      this.background(this.flush());
      return;
    }
    this.scheduleSyncDebounced();
  }

  dropBlockedChanges(): void {
    this.queue = withoutBlockedSearchChanges(this.queue);
  }

  /** 强制立即同步 */
  async forceSync(): Promise<SyncResult> {
    this.cancelScheduledSync();
    return this.flush();
  }

  /**
   * 启动时先整理浏览器存储里上次留下的队列：无从归属账号的积压丢弃（不能确认是这个账号的编辑）；
   * 含密钥的条目不能在后端不可达期间继续明文留在存储里，先移进内存。
   */
  prepareStoredQueue(): void {
    discardUnattributedOfflineQueue();
    this.memoryOnlyOfflineChanges.push(...takeUnpersistableOfflineEntries());
  }

  /** 待重放的离线变更：内存里的非白名单条目 + 浏览器存储里的白名单条目；队列已持有同键不更旧写入的，由队列自己发送。 */
  collectOfflineChanges(): ConfigChange[] {
    const queued = (entry: ConfigChange) =>
      this.queue.some((change) => change.key === entry.key && change.timestamp >= entry.timestamp);
    return [...this.memoryOnlyOfflineChanges, ...loadOfflineQueue()].filter((entry) => !queued(entry));
  }

  /** Replays the leftovers of a previous session, each change judged on its own against what the server holds. */
  async replayOfflineChanges(pending: ConfigChange[]): Promise<void> {
    if (pending.length === 0) {
      return;
    }
    console.warn(`[ConfigSync] Found ${pending.length} offline changes, syncing...`);
    const unread = await this.unreadKeys(pending);
    const { baseCache, resolver } = this.host.context();
    const { send, settled, undecided } = await decideReplay(pending, baseCache, unread, resolver);
    // 内存里只留未决的条目：已决定的完成了使命，队列已持有同键不更旧写入的由那次写入取代。
    this.memoryOnlyOfflineChanges = this.memoryOnlyOfflineChanges.filter((change) => undecided.includes(change));
    removeOfflineEntries(settled);
    if (send.length > 0) {
      const sink = this.host.context();
      applyReplayedChanges(sink, sink.deviceId, send);
      this.queue.unshift(...send);
      await this.flush();
    }
    if (undecided.length > 0) {
      this.host.setStatus('offline');
    }
  }

  /** 渐进加载下缓存只含核心键：队列里的非核心键没补载入就比对，会把「没取到」当成「服务端已前进」。 */
  private async unreadKeys(changes: ConfigChange[]): Promise<Set<ConfigKey>> {
    const keys = [...new Set(changes.map((change) => change.key))];
    const known = await Promise.all(keys.map((key) => this.host.ensureKeyLoaded(key)));
    return new Set(keys.filter((_key, index) => !known[index]));
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
    this.retry.cancel();
    if (typeof window !== 'undefined') {
      window.removeEventListener('online', this.handleOnline);
    }
    this.onlineHandlerRegistered = false;
  }

  /** Edit times order two edits of one key in the store, so no two edits share one. */
  private stamped(change: ConfigChange): ConfigChange {
    this.lastEditTime = Math.max(change.timestamp, this.lastEditTime + 1);
    return { ...change, timestamp: this.lastEditTime };
  }

  /** 防抖同步 */
  private scheduleSyncDebounced(): void {
    this.cancelScheduledSync();
    this.syncDebounceTimer = setTimeout(() => {
      this.background(this.flush());
    }, SYNC_DEBOUNCE_MS);
  }

  /** A send nobody awaits: its refusal was logged where it happened, so it must not end as an unhandled rejection. */
  private background(task: Promise<unknown>): void {
    task.catch(() => undefined);
  }

  private cancelScheduledSync(): void {
    if (this.syncDebounceTimer) {
      clearTimeout(this.syncDebounceTimer);
      this.syncDebounceTimer = null;
    }
  }

  /** Sends what is queued; returns once the answer is applied and every clash it raised is settled. */
  private async flush(): Promise<SyncResult> {
    const delivery = await this.exclusive(() => this.sendQueued());
    await delivery.settled;
    if ('refusal' in delivery) {
      throw delivery.refusal;
    }
    return delivery.result;
  }

  /** Runs `task` after every earlier send has ended; a failed send does not stop the chain. */
  private exclusive<T>(task: () => Promise<T>): Promise<T> {
    const run = this.lastSend.then(task);
    this.lastSend = run.catch(() => undefined);
    return run;
  }

  /** One batch of the queued changes whose key is not being settled: the latest value per key. */
  private sendQueued(): Promise<Delivery> {
    this.queue = withoutBlockedSearchChanges(this.queue);
    const ready = this.queue.filter((change) => !this.clashing.has(change.key));
    if (ready.length === 0) {
      return Promise.resolve(nothingSent());
    }
    this.queue = this.queue.filter((change) => this.clashing.has(change.key));
    const batch = mergeLatestChanges(ready, this.host.context().baseCache);
    return this.deliver(batch);
  }

  private async deliver(batch: ConfigChange[]): Promise<Delivery> {
    this.host.setStatus('syncing');
    let result: SyncResult;
    try {
      result = await this.host.context().adapter.sync(batch);
    } catch (error) {
      // 适配器把传输失败折算成失败结果（见 `adapters/_ARCH.md`），走到这里的是后端明确拒绝的写入。
      console.warn('[ConfigSync] Sync failed:', error);
      return this.isolate(batch, error);
    }
    return { result, settled: this.settle(batch, result, true) };
  }

  /**
   * The backend validates a whole batch before it stores any change, so its refusal does not say which change it
   * dislikes: each key is sent alone. The keys it takes are settled like any answer, only the keys it refuses lose
   * their write, and the refusal of the batch is what the caller of `forceSync()` sees.
   */
  private async isolate(batch: ConfigChange[], refusal: unknown): Promise<Delivery> {
    if (batch.length === 1) {
      removeOfflineEntries(batch);
      this.host.setStatus('error');
      return { refusal, settled: Promise.resolve() };
    }
    const answers: SyncResult[] = [];
    const settlements: Array<Promise<void>> = [];
    let refused = false;
    for (const change of batch) {
      try {
        const answer = await this.host.context().adapter.sync([change]);
        answers.push(answer);
        settlements.push(this.settle([change], answer, true));
      } catch (error) {
        console.warn(`[ConfigSync] The backend refused the change of '${change.key}':`, error);
        removeOfflineEntries([change]);
        refused = true;
      }
    }
    const settled = Promise.all(settlements).then(() => undefined);
    if (refused) {
      this.host.setStatus('error');
      return { refusal, settled };
    }
    return { result: mergeAnswers(answers), settled };
  }

  /**
   * Applies an answer to the batch it answers. Accepted keys are acknowledged; clashing keys go to the resolver
   * (`resolveClashes`) or, on a re-send, wait for the next flush; keys the answer does not name stay queued.
   */
  private async settle(batch: ConfigChange[], result: SyncResult, resolveClashes: boolean): Promise<void> {
    if (!result.error) {
      this.retry.reset();
    }
    const { accepted, rejected, unnamed } = partitionByAnswer(batch, result);
    this.acknowledge(accepted, result.newVersions);

    if (result.conflicts.length > 0 && resolveClashes) {
      this.retain(unnamed);
      await this.reconcile(rejected, result.conflicts);
      return;
    }
    if (result.error) {
      console.warn('[ConfigSync] Sync failed:', result.error);
      if (!isRecoverableSyncError(result.error)) {
        removeOfflineEntries([...rejected, ...unnamed]);
        this.host.setStatus('error');
        return;
      }
    }
    this.retain([...rejected, ...unnamed]);
    this.host.setStatus(result.error ? 'offline' : 'idle');
  }

  /** The backend accepted these: the merge base moves to what it holds, and the stored copies they cover go. */
  private acknowledge(accepted: ConfigChange[], versions: ReadonlyMap<ConfigKey, ConfigVersion>): void {
    if (accepted.length === 0) {
      return;
    }
    const sink = this.host.context();
    recordSyncedChanges(sink, sink.deviceId, accepted, versions);
    removeOfflineEntries(accepted);
  }

  /**
   * Keeps changes the backend did not take: queued again, stored again (allowlisted keys), retried with backoff.
   * They go in front of the queue so a newer edit of the same key stays the latest.
   */
  private retain(changes: ConfigChange[]): void {
    if (changes.length === 0) {
      return;
    }
    this.queue.unshift(...changes);
    saveOfflineQueue(changes);
    this.retry.schedule();
  }

  /**
   * Settles the clashing keys with the server: the local values that are kept are re-sent, the others give way to the
   * server's. Newer edits of these keys wait in the queue meanwhile; the re-send is one more batch of the same chain,
   * so nothing overtakes it.
   */
  private async reconcile(rejected: ConfigChange[], keys: ConfigKey[]): Promise<void> {
    for (const key of keys) {
      this.clashing.add(key);
    }
    // The re-sent value is the cached one, the latest edit made so far: it settles the stored copies up to that edit
    // and not those of edits made while the user decides.
    const editedAt = new Map<ConfigKey, number>();
    for (const change of [...rejected, ...this.queue]) {
      editedAt.set(change.key, Math.max(editedAt.get(change.key) ?? 0, change.timestamp));
    }
    try {
      const { resend, adopted, unresolved } = await resolveConflicts(this.host.context(), keys);
      this.retain(rejected.filter((change) => unresolved.includes(change.key)));
      // The server's value won for the adopted keys: the edits the user was shown are void, stored copies included.
      const overruled = (change: ConfigChange) =>
        adopted.includes(change.key) && change.timestamp <= (editedAt.get(change.key) ?? 0);
      removeOfflineEntries([...rejected, ...this.queue].filter(overruled));
      this.queue = this.queue.filter((change) => !overruled(change));
      if (resend.length > 0) {
        const edits = resend.map((change) => ({ ...change, timestamp: editedAt.get(change.key) ?? change.timestamp }));
        await this.exclusive(() => this.resend(edits));
      } else {
        this.host.setStatus(unresolved.length > 0 ? 'offline' : 'idle');
      }
    } finally {
      for (const key of keys) {
        this.clashing.delete(key);
      }
      if (this.queue.length > 0) {
        this.scheduleSyncDebounced();
      }
    }
  }

  private async resend(changes: ConfigChange[]): Promise<void> {
    try {
      const result = await this.host.context().adapter.sync(changes);
      await this.settle(changes, result, false);
    } catch (error) {
      console.warn('[ConfigSync] Conflict retry error, saving to offline queue:', error);
      this.retain(changes);
      this.host.setStatus('offline');
    }
  }

  private async retryOfflineQueue(): Promise<void> {
    // 启动失败时服务端状态从未载入：先重新初始化（它自己会载入并重放队列），仍不可达就留在队列里等下一次联网。
    await this.host.initialize();
    if (!this.host.isInitialized()) {
      return;
    }
    await this.replayOfflineChanges(this.collectOfflineChanges());
    if (this.queue.length > 0) {
      await this.flush();
    }
  }
}
