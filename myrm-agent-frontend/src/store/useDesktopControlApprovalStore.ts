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
    messageId?: string;
  }) => void;
  clear: () => void;
}

const useDesktopControlApprovalStore = create<DesktopControlApprovalState>((set) => ({
  pending: false,
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
      requestId: payload.request_id,
      reason: payload.reason,
      operation: payload.operation,
      appName: payload.app_name ?? '',
      windowTitle: payload.window_title ?? '',
      requireAppApproval: payload.require_app_approval ?? true,
      messageId: payload.messageId ?? '',
      requestedAt: Date.now(),
    }),

  clear: () =>
    set({
      pending: false,
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
