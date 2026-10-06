/**
 * [INPUT]
 * Browser BroadcastChannel API or window CustomEvent fallback
 *
 * [OUTPUT]
 * MultiWindowCanvasStateBus: Cross-window/cross-tab state event bus
 * CanvasBusEvent: Discriminated union of cross-window synchronization events
 *
 * [POS]
 * myrm-agent-frontend/src/lib/canvasBus/multiWindowCanvasStateBus.ts
 * Cross-window multi-session canvas state bus ensuring sub-millisecond synchronization.
 */

export type CanvasBusEventType =
  | 'SESSION_FOCUS'
  | 'CANVAS_STATE_UPDATE'
  | 'TOOL_EXECUTION_SYNC'
  | 'CONFIG_SYNC';

export interface BaseCanvasBusPayload {
  readonly senderWindowId: string;
  readonly timestamp: number;
}

export interface SessionFocusEvent extends BaseCanvasBusPayload {
  readonly type: 'SESSION_FOCUS';
  readonly sessionId: string;
  readonly activeTabId?: string;
}

export interface CanvasStateUpdateEvent extends BaseCanvasBusPayload {
  readonly type: 'CANVAS_STATE_UPDATE';
  readonly canvasId: string;
  readonly nodeCount: number;
  readonly activeArtifactId?: string;
  readonly revision: number;
}

export interface ToolExecutionSyncEvent extends BaseCanvasBusPayload {
  readonly type: 'TOOL_EXECUTION_SYNC';
  readonly callId: string;
  readonly toolName: string;
  readonly status: 'running' | 'completed' | 'failed';
  readonly summary?: string;
}

export interface ConfigSyncEvent extends BaseCanvasBusPayload {
  readonly type: 'CONFIG_SYNC';
  readonly scope: 'model' | 'theme' | 'general';
  readonly key: string;
  readonly value: string | number | boolean;
}

export type CanvasBusEvent =
  | SessionFocusEvent
  | CanvasStateUpdateEvent
  | ToolExecutionSyncEvent
  | ConfigSyncEvent;

export type CanvasBusEventHandler<T extends CanvasBusEvent = CanvasBusEvent> = (event: T) => void;

const DEFAULT_CHANNEL_NAME = 'myrm_canvas_state_bus_v1';

export class MultiWindowCanvasStateBus {
  private static instance: MultiWindowCanvasStateBus | null = null;

  public readonly windowInstanceId: string;
  private readonly channelName: string;
  private broadcastChannel: BroadcastChannel | null = null;
  private readonly listeners = new Map<CanvasBusEventType, Set<CanvasBusEventHandler>>();
  private isDestroyed = false;

  public constructor(channelName: string = DEFAULT_CHANNEL_NAME) {
    this.channelName = channelName;
    this.windowInstanceId = `win_${Math.random().toString(36).substring(2, 10)}_${Date.now()}`;
    this.initTransport();
  }

  public static getInstance(channelName: string = DEFAULT_CHANNEL_NAME): MultiWindowCanvasStateBus {
    if (!MultiWindowCanvasStateBus.instance) {
      MultiWindowCanvasStateBus.instance = new MultiWindowCanvasStateBus(channelName);
    }
    return MultiWindowCanvasStateBus.instance;
  }

  public static resetInstance(): void {
    if (MultiWindowCanvasStateBus.instance) {
      MultiWindowCanvasStateBus.instance.destroy();
      MultiWindowCanvasStateBus.instance = null;
    }
  }

  private initTransport(): void {
    if (typeof window !== 'undefined' && typeof window.BroadcastChannel !== 'undefined') {
      try {
        this.broadcastChannel = new window.BroadcastChannel(this.channelName);
        this.broadcastChannel.onmessage = (messageEvent: MessageEvent<CanvasBusEvent>): void => {
          this.handleIncomingMessage(messageEvent.data);
        };
      } catch {
        // Fallback to local memory event bus if BroadcastChannel is blocked
        this.broadcastChannel = null;
      }
    }
  }

  public handleIncomingMessageForTest(event: CanvasBusEvent): void {
    this.handleIncomingMessage(event);
  }

  private handleIncomingMessage(event: CanvasBusEvent): void {
    if (this.isDestroyed || !event || event.senderWindowId === this.windowInstanceId) {
      // Loopback prevention: Ignore own messages
      return;
    }
    this.dispatchLocal(event);
  }

  private dispatchLocal(event: CanvasBusEvent): void {
    const handlers = this.listeners.get(event.type);
    if (!handlers || handlers.size === 0) {
      return;
    }
    for (const handler of handlers) {
      try {
        handler(event);
      } catch (err: unknown) {
        console.error(`[MultiWindowCanvasStateBus] Error executing listener for ${event.type}:`, err);
      }
    }
  }

  public publish(
    event: Omit<SessionFocusEvent, 'senderWindowId' | 'timestamp'>
      | Omit<CanvasStateUpdateEvent, 'senderWindowId' | 'timestamp'>
      | Omit<ToolExecutionSyncEvent, 'senderWindowId' | 'timestamp'>
      | Omit<ConfigSyncEvent, 'senderWindowId' | 'timestamp'>,
  ): void {
    if (this.isDestroyed) {
      return;
    }

    const envelope = {
      ...event,
      senderWindowId: this.windowInstanceId,
      timestamp: Date.now(),
    } as CanvasBusEvent;

    // 1. Broadcast to other tabs/windows
    if (this.broadcastChannel) {
      try {
        this.broadcastChannel.postMessage(envelope);
      } catch (err: unknown) {
        console.warn('[MultiWindowCanvasStateBus] broadcast postMessage failed:', err);
      }
    }

    // 2. Dispatch to local subscribers in the current window as well
    this.dispatchLocal(envelope);
  }

  public subscribe<T extends CanvasBusEvent>(
    type: T['type'],
    handler: CanvasBusEventHandler<T>,
  ): () => void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    const handlers = this.listeners.get(type)!;
    const genericHandler = handler as CanvasBusEventHandler;
    handlers.add(genericHandler);

    return (): void => {
      handlers.delete(genericHandler);
      if (handlers.size === 0) {
        this.listeners.delete(type);
      }
    };
  }

  public destroy(): void {
    if (this.isDestroyed) {
      return;
    }
    this.isDestroyed = true;
    if (this.broadcastChannel) {
      this.broadcastChannel.close();
      this.broadcastChannel = null;
    }
    this.listeners.clear();
  }
}
