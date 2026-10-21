/**
 * 前端集中式连接状态控制器 (ConnectionController)。
 *
 * 汲取 DeepSeek Harness 2026-08-28 `web-connection-recovery-control` 核心生产实践：
 * 1. ConnectionController 是前端唯一的 retry 调度器，接管 WebSocket / SSE 连接生命周期；
 * 2. 浏览器事件联动：监听 offline 立即中断连接并暂停重试，监听 online 立即发布 connecting 并从 500ms 重新发起；
 * 3. 严格防抖的用户态“立即重连”：点击立即重置退避阶梯并从物理层立即发起重连；
 * 4. 纯 TypeScript 实现，完全解耦 React 渲染层，支持 SSR 与跨端（Web/Tauri/Node）。
 */

import { JitteredBackoffScheduler } from './jitter-backoff';

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected';

export type ConnectionStateListener = (status: ConnectionStatus) => void;

export interface ConnectionControllerOptions {
  scheduler?: JitteredBackoffScheduler;
  connectTransport?: () => Promise<void> | void;
  disconnectTransport?: () => void;
}

export class ConnectionController {
  private static instance: ConnectionController | null = null;

  private readonly scheduler: JitteredBackoffScheduler;
  private readonly connectTransport?: () => Promise<void> | void;
  private readonly disconnectTransport?: () => void;

  private currentStatus: ConnectionStatus = 'disconnected';
  private isOnline: boolean = true;
  private listeners: Set<ConnectionStateListener> = new Set();
  private pendingRetryTimer: ReturnType<typeof setTimeout> | null = null;
  private lastReconnectTriggerTime: number = 0;

  constructor(options?: ConnectionControllerOptions) {
    this.scheduler = options?.scheduler ?? new JitteredBackoffScheduler();
    this.connectTransport = options?.connectTransport;
    this.disconnectTransport = options?.disconnectTransport;

    this.initBrowserNetworkBinding();
  }

  public static getInstance(): ConnectionController {
    if (!ConnectionController.instance) {
      ConnectionController.instance = new ConnectionController();
    }
    return ConnectionController.instance;
  }

  public get status(): ConnectionStatus {
    return this.currentStatus;
  }

  public get online(): boolean {
    return this.isOnline;
  }

  public subscribe(listener: ConnectionStateListener): () => void {
    this.listeners.add(listener);
    // 立即以当前状态通知新订阅者
    listener(this.currentStatus);

    return () => {
      this.listeners.delete(listener);
    };
  }

  private setStatus(newStatus: ConnectionStatus): void {
    if (this.currentStatus === newStatus) {
      return;
    }
    this.currentStatus = newStatus;
    for (const listener of this.listeners) {
      try {
        listener(newStatus);
      } catch (err) {
        console.error('[ConnectionController] Error in state listener:', err);
      }
    }
  }

  private clearPendingTimer(): void {
    if (this.pendingRetryTimer !== null) {
      clearTimeout(this.pendingRetryTimer);
      this.pendingRetryTimer = null;
    }
  }

  /**
   * 物理层建立连接成功时调用。
   */
  public markConnected(): void {
    this.clearPendingTimer();
    this.scheduler.reset();
    this.setStatus('connected');
  }

  /**
   * 物理层传输中断或报错时调用。
   */
  public markDisconnected(): void {
    this.clearPendingTimer();

    // 若系统已离线，直接停留在 disconnected
    if (!this.isOnline) {
      this.setStatus('disconnected');
      return;
    }

    const delayMs = this.scheduler.nextDelayMs();
    if (this.scheduler.isExhausted() || delayMs <= 0) {
      // 达到 10s 档重试失败后停止盲目重试，等待用户手动点击“立即重连”
      this.setStatus('disconnected');
      return;
    }

    // 进入正在重连状态，并在延迟后发起物理重试
    this.setStatus('connecting');
    this.pendingRetryTimer = setTimeout(() => {
      this.executePhysicalConnect();
    }, delayMs);
  }

  /**
   * 用户态显式点击“立即重连”：打断当前等待、重置退避并立即发起物理直连。
   */
  public reconnectNow(): boolean {
    const now = Date.now();
    // 500ms CAS 严格防抖，杜绝疯狂连击冲突
    if (now - this.lastReconnectTriggerTime < 500) {
      return false;
    }

    this.lastReconnectTriggerTime = now;
    this.clearPendingTimer();
    this.scheduler.reset();
    this.setStatus('connecting');

    this.executePhysicalConnect();
    return true;
  }

  private executePhysicalConnect(): void {
    if (this.connectTransport) {
      try {
        const result = this.connectTransport();
        if (result instanceof Promise) {
          result.catch(() => {
            this.markDisconnected();
          });
        }
      } catch {
        this.markDisconnected();
      }
    }
  }

  private initBrowserNetworkBinding(): void {
    if (typeof window === 'undefined' || typeof window.addEventListener !== 'function') {
      return;
    }

    this.isOnline = typeof navigator !== 'undefined' ? navigator.onLine : true;

    window.addEventListener('offline', () => {
      this.isOnline = false;
      this.clearPendingTimer();
      if (this.disconnectTransport) {
        try {
          this.disconnectTransport();
        } catch {
          // 容错处理
        }
      }
      this.setStatus('disconnected');
    });

    window.addEventListener('online', () => {
      this.isOnline = true;
      this.reconnectNow();
    });
  }

  public destroy(): void {
    this.clearPendingTimer();
    this.listeners.clear();
  }
}
