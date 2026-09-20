/**
 * [INPUT]
 * - zustand::create (POS: Lightweight state management)
 *
 * [OUTPUT]
 * useDesktopControlApprovalStore: pending desktop control approval card state.
 *
 * [POS]
 * Manages SSE-driven desktop control approval requests (per-app + foreground gate).
 */

import { create } from 'zustand';

export type DesktopControlApprovalScope = 'once' | 'session' | 'always';

interface DesktopControlApprovalState {
  pending: boolean;
  expired: boolean;
  denied: boolean;
  changed: boolean;
  requestId: string;
  reason: string;
  operation: string;
  appName: string;
  windowTitle: string;
  requireAppApproval: boolean;
  messageId: string;
  requestedAt: number;

  requestApproval: (payload: {
    request_id: string;
    reason: string;
    operation: string;
    app_name?: string;
    window_title?: string;
    require_app_approval?: boolean;
    changed_since_last_grant?: boolean;
    messageId?: string;
  }) => void;
  markExpired: () => void;
  markDenied: () => void;
  clear: () => void;
}

const useDesktopControlApprovalStore = create<DesktopControlApprovalState>((set) => ({
  pending: false,
  expired: false,
  denied: false,
  changed: false,
  requestId: '',
  reason: '',
  operation: '',
  appName: '',
  windowTitle: '',
  requireAppApproval: true,
  messageId: '',
  requestedAt: 0,

  requestApproval: (payload) =>
    set({
      pending: true,
      expired: false,
      denied: false,
      changed: Boolean(payload.changed_since_last_grant ?? false),
      requestId: payload.request_id,
      reason: payload.reason,
      operation: payload.operation,
      appName: payload.app_name ?? '',
      windowTitle: payload.window_title ?? '',
      requireAppApproval: payload.require_app_approval ?? true,
      messageId: payload.messageId ?? '',
      requestedAt: Date.now(),
    }),

  markExpired: () => set({ expired: true }),

  markDenied: () => set({ denied: true }),

  clear: () =>
    set({
      pending: false,
      expired: false,
      denied: false,
      changed: false,
      requestId: '',
      reason: '',
      operation: '',
      appName: '',
      windowTitle: '',
      requireAppApproval: true,
      messageId: '',
    }),
}));

export default useDesktopControlApprovalStore;
