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

export type DesktopControlApprovalScope = 'once' | 'session' | 'always' | 'envelope';

export interface ActiveEnvelopeState {
  taskId: string;
  allowedApps: string[];
  maxActions: number;
  usedActions: number;
  remainingBudget: number;
  allowSystemDialogs: boolean;
  status: 'pending_consent' | 'active' | 'escalated' | 'exhausted' | 'completed';
  escalationReason?: string;
  canExtend?: boolean;
  hardLimit?: number;
}

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

  activeEnvelope: ActiveEnvelopeState | null;

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

  setEnvelope: (envelope: ActiveEnvelopeState | null) => void;
  updateEnvelopeProgress: (payload: {
    used: number;
    max: number;
    remaining?: number;
    canExtend?: boolean;
    hardLimit?: number;
  }) => void;
  extendEnvelopeLease: (additionalSteps?: number) => void;
  escalateEnvelope: (reason: string) => void;
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
  activeEnvelope: null,

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

  setEnvelope: (envelope) => set({ activeEnvelope: envelope }),

  updateEnvelopeProgress: ({ used, max, remaining, canExtend, hardLimit }) =>
    set((state) => {
      if (!state.activeEnvelope) {
        return {};
      }
      const rem = remaining !== undefined ? remaining : Math.max(0, max - used);
      const isExhausted = used >= max;
      return {
        activeEnvelope: {
          ...state.activeEnvelope,
          usedActions: used,
          maxActions: max,
          remainingBudget: rem,
          status: isExhausted ? 'exhausted' : state.activeEnvelope.status,
          canExtend: canExtend !== undefined ? canExtend : state.activeEnvelope.canExtend,
          hardLimit: hardLimit !== undefined ? hardLimit : state.activeEnvelope.hardLimit,
        },
      };
    }),

  extendEnvelopeLease: (additionalSteps = 10) =>
    set((state) => {
      if (!state.activeEnvelope) {
        return {};
      }
      const newMax = state.activeEnvelope.maxActions + Math.max(1, additionalSteps);
      return {
        activeEnvelope: {
          ...state.activeEnvelope,
          maxActions: newMax,
          remainingBudget: Math.max(0, newMax - state.activeEnvelope.usedActions),
          status: 'active',
        },
      };
    }),

  escalateEnvelope: (reason) =>
    set((state) => {
      if (!state.activeEnvelope) {
        return {};
      }
      return {
        activeEnvelope: {
          ...state.activeEnvelope,
          status: 'escalated',
          escalationReason: reason,
        },
      };
    }),
}));

export default useDesktopControlApprovalStore;
