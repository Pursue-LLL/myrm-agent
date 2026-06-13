/**
 * [INPUT]
 * - zustand::create (POS: Lightweight state management)
 *
 * [OUTPUT]
 * useBrowserTakeoverStore: Zustand store for browser takeover request state.
 *
 * [POS]
 * Manages the state when Agent requests human takeover of the browser session.
 * SSE handler sets pending=true with reason+messageId; VisualDesktopToggle
 * auto-opens VNC panel and provides a "done" button that triggers resume.
 */

import { create } from 'zustand';

interface BrowserTakeoverState {
  pending: boolean;
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
  }) => void;
  completeTakeover: () => void;
  dismiss: () => void;
}

const useBrowserTakeoverStore = create<BrowserTakeoverState>((set) => ({
  pending: false,
  reason: '',
  screenshotBase64: null,
  url: '',
  messageId: '',
  requestedAt: 0,

  requestTakeover: (payload) =>
    set({
      pending: true,
      reason: payload.reason,
      screenshotBase64: payload.screenshot_base64 ?? null,
      url: payload.url ?? '',
      messageId: payload.messageId ?? '',
      requestedAt: Date.now(),
    }),

  completeTakeover: () =>
    set({
      pending: false,
      reason: '',
      screenshotBase64: null,
      url: '',
      messageId: '',
    }),

  dismiss: () =>
    set({
      pending: false,
      reason: '',
      screenshotBase64: null,
      url: '',
      messageId: '',
    }),
}));

export default useBrowserTakeoverStore;
