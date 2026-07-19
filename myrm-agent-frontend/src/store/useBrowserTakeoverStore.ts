/**
 * [INPUT]
 * - zustand::create (POS: Lightweight state management)
 *
 * [OUTPUT]
 * useBrowserTakeoverStore: Zustand store for browser takeover request state.
 *
 * [POS]
 * Manages the state when Agent requests human takeover of the browser session.
 * SSE handler sets pending=true with reason+messageId; managed mode uses
 * VisualDesktopToggle (VNC); extension mode uses ExtensionTakeoverBanner (in-chat).
 */

import { create } from 'zustand';

export type BrowserTakeoverUiMode = 'managed' | 'extension';

const IDLE_TAKEOVER_STATE = {
  pending: false,
  uiMode: 'managed' as BrowserTakeoverUiMode,
  autoDetectCompletion: false,
  reason: '',
  screenshotBase64: null as string | null,
  url: '',
  messageId: '',
  requestedAt: 0,
};

interface BrowserTakeoverState {
  pending: boolean;
  uiMode: BrowserTakeoverUiMode;
  autoDetectCompletion: boolean;
  reason: string;
  screenshotBase64: string | null;
  url: string;
  messageId: string;
  requestedAt: number;

  requestTakeover: (payload: {
    reason: string;
    screenshot_base64?: string | null;
    url?: string;
    messageId?: string;
    ui_mode?: BrowserTakeoverUiMode;
    auto_detect_completion?: boolean;
  }) => void;
  completeTakeover: () => void;
  dismiss: () => void;
}

const useBrowserTakeoverStore = create<BrowserTakeoverState>((set) => ({
  ...IDLE_TAKEOVER_STATE,

  requestTakeover: (payload) =>
    set({
      pending: true,
      uiMode: payload.ui_mode ?? 'managed',
      autoDetectCompletion: payload.auto_detect_completion ?? false,
      reason: payload.reason,
      screenshotBase64: payload.screenshot_base64 ?? null,
      url: payload.url ?? '',
      messageId: payload.messageId ?? '',
      requestedAt: Date.now(),
    }),

  completeTakeover: () => set({ ...IDLE_TAKEOVER_STATE }),

  dismiss: () => set({ ...IDLE_TAKEOVER_STATE }),
}));

export default useBrowserTakeoverStore;
