import { create } from 'zustand';
import {
  ControlMode,
  DesktopActionTelemetry,
  EphemeralShareTicket,
  ShareOptions,
  StreamConnectionState,
  StreamQualityMetrics,
} from './remoteDesktopTypes';
import { generateEphemeralShareTicket } from './ephemeralTokenSecurity';

export interface RemoteDesktopState {
  connectionState: StreamConnectionState;
  controlMode: ControlMode;
  sandboxId: string;
  streamMetrics: StreamQualityMetrics;
  actionHistory: DesktopActionTelemetry[];
  isShareModalOpen: boolean;
  currentTicket: EphemeralShareTicket | null;
  isTakeoverAlertActive: boolean;
  takeoverReason: string | null;
  isStreamMuted: boolean;
  isExpanded: boolean;

  // Actions
  connectStream: (sandboxId?: string) => Promise<void>;
  disconnectStream: () => void;
  pauseStream: () => void;
  resumeStream: () => void;
  requestHumanTakeover: (reason?: string) => void;
  releaseHumanTakeover: () => void;
  openShareModal: () => void;
  closeShareModal: () => void;
  createShareTicket: (options: ShareOptions) => EphemeralShareTicket;
  toggleExpanded: () => void;
  pushActionTelemetry: (
    action: Omit<DesktopActionTelemetry, 'id' | 'timestamp'>
  ) => void;
  resetState: () => void;
}

const DEFAULT_METRICS: StreamQualityMetrics = {
  fps: 30,
  latencyMs: 24,
  bitrateKbps: 2400,
  resolution: '1920x1080',
};

const INITIAL_ACTIONS: DesktopActionTelemetry[] = [
  {
    id: 'act-1',
    actionType: 'navigate',
    description: '打开目标竞品门户并初始化页面上下文',
    timestamp: Date.now() - 15000,
  },
  {
    id: 'act-2',
    actionType: 'click',
    description: '点击搜索栏并输入定位选择器',
    coordinates: { x: 450, y: 120 },
    timestamp: Date.now() - 10000,
  },
  {
    id: 'act-3',
    actionType: 'scroll',
    description: '模拟人类浏览平滑向下滚动 600px',
    timestamp: Date.now() - 5000,
  },
];

export const useRemoteDesktopStore = create<RemoteDesktopState>((set, get) => ({
  connectionState: 'streaming',
  controlMode: 'observer',
  sandboxId: 'sandbox-cloud-vm-8891',
  streamMetrics: DEFAULT_METRICS,
  actionHistory: INITIAL_ACTIONS,
  isShareModalOpen: false,
  currentTicket: null,
  isTakeoverAlertActive: false,
  takeoverReason: null,
  isStreamMuted: false,
  isExpanded: false,

  connectStream: async (sandboxId) => {
    const targetId = sandboxId || get().sandboxId;
    set({ connectionState: 'connecting', sandboxId: targetId });

    await new Promise((resolve) => setTimeout(resolve, 60));

    set({
      connectionState: 'streaming',
      controlMode: 'observer',
      streamMetrics: { ...DEFAULT_METRICS, latencyMs: 22 },
    });
  },

  disconnectStream: () => {
    set({
      connectionState: 'disconnected',
      controlMode: 'observer',
      isTakeoverAlertActive: false,
    });
  },

  pauseStream: () => {
    set({ connectionState: 'paused' });
  },

  resumeStream: () => {
    set({ connectionState: 'streaming' });
  },

  requestHumanTakeover: (reason) => {
    const defaultReason = reason || '检测到复杂图形验证码，请求人工接管操作';
    set({
      controlMode: 'human-takeover',
      isTakeoverAlertActive: true,
      takeoverReason: defaultReason,
    });

    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('myrm:remote-desktop-takeover-changed', {
          detail: {
            mode: 'human-takeover',
            sandboxId: get().sandboxId,
            reason: defaultReason,
            timestamp: Date.now(),
          },
        })
      );
    }
  },

  releaseHumanTakeover: () => {
    set({
      controlMode: 'observer',
      isTakeoverAlertActive: false,
      takeoverReason: null,
    });

    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('myrm:remote-desktop-takeover-changed', {
          detail: {
            mode: 'observer',
            sandboxId: get().sandboxId,
            timestamp: Date.now(),
          },
        })
      );
    }
  },

  openShareModal: () => {
    if (!get().currentTicket) {
      const ticket = generateEphemeralShareTicket(get().sandboxId, {
        ttlSeconds: 7200, // 默认 2 小时
        allowTakeover: false,
        oneTimeOnly: false,
      });
      set({ currentTicket: ticket });
    }
    set({ isShareModalOpen: true });
  },

  closeShareModal: () => {
    set({ isShareModalOpen: false });
  },

  createShareTicket: (options) => {
    const ticket = generateEphemeralShareTicket(get().sandboxId, options);
    set({ currentTicket: ticket });

    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('myrm:ephemeral-share-created', {
          detail: {
            ticketId: ticket.ticketId,
            sandboxId: ticket.sandboxId,
            expiresAt: ticket.expiresAt,
            url: ticket.url,
          },
        })
      );
    }

    return ticket;
  },

  toggleExpanded: () => {
    set((state) => ({ isExpanded: !state.isExpanded }));
  },

  pushActionTelemetry: (action) => {
    const item: DesktopActionTelemetry = {
      ...action,
      id: `act-${Date.now()}`,
      timestamp: Date.now(),
    };
    set((state) => ({
      actionHistory: [item, ...state.actionHistory].slice(0, 30),
    }));
  },

  resetState: () => {
    set({
      connectionState: 'streaming',
      controlMode: 'observer',
      sandboxId: 'sandbox-cloud-vm-8891',
      streamMetrics: DEFAULT_METRICS,
      actionHistory: INITIAL_ACTIONS,
      isShareModalOpen: false,
      currentTicket: null,
      isTakeoverAlertActive: false,
      takeoverReason: null,
      isStreamMuted: false,
      isExpanded: false,
    });
  },
}));
