/**
 * [INPUT]
 * - canvasSecurityTypes: CanvasEgressRequest, CanvasSecurityAuditEvent, CanvasPermissionStatus
 *
 * [OUTPUT]
 * - useCanvasGatingStore: Zustand store for Canvas security gating & domain allowlists
 *
 * [POS]
 * Store for Canvas safe sandboxing and interactive script gating (Item 44 P0).
 * Strictly under 200 lines. Zero `any`.
 */

import { create } from 'zustand';
import type {
  CanvasAuditEventType,
  CanvasEgressRequest,
  CanvasSecurityAuditEvent,
} from './canvasSecurityTypes';

interface CanvasGatingState {
  allowedDomains: string[];
  pendingRequests: CanvasEgressRequest[];
  auditLogs: CanvasSecurityAuditEvent[];

  isDomainAllowed: (domain: string) => boolean;
  registerEgressRequest: (
    req: Omit<CanvasEgressRequest, 'id' | 'timestamp' | 'status'>
  ) => { allowed: boolean; requestId: string };
  approveRequest: (requestId: string, persistDomain?: boolean) => void;
  denyRequest: (requestId: string) => void;
  addAuditLog: (type: CanvasAuditEventType, detail: string, domain?: string) => void;
  clearAuditLogs: () => void;
  reset: () => void;
}

export const useCanvasGatingStore = create<CanvasGatingState>((set, get) => ({
  allowedDomains: [],
  pendingRequests: [],
  auditLogs: [],

  isDomainAllowed: (domain: string) => {
    const normalized = domain.toLowerCase().trim();
    if (!normalized) {
      return false;
    }
    return get().allowedDomains.includes(normalized);
  },

  registerEgressRequest: (req) => {
    const id = `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const domain = req.domain.toLowerCase().trim();
    const isAllowed = get().isDomainAllowed(domain);

    const fullRequest: CanvasEgressRequest = {
      ...req,
      id,
      timestamp: Date.now(),
      status: isAllowed ? 'allowed' : 'pending',
    };

    if (isAllowed) {
      get().addAuditLog(
        'egress-allowed',
        `Auto-allowed egress request to pre-whitelisted domain: ${domain}`,
        domain
      );
      return { allowed: true, requestId: id };
    }

    set((state) => ({
      pendingRequests: [...state.pendingRequests, fullRequest],
    }));

    get().addAuditLog(
      'egress-requested',
      `Canvas requested external egress to: ${domain} (${req.method} ${req.url})`,
      domain
    );

    return { allowed: false, requestId: id };
  },

  approveRequest: (requestId: string, persistDomain = false) => {
    const target = get().pendingRequests.find((r) => r.id === requestId);
    if (!target) {
      return;
    }

    set((state) => {
      const nextPending = state.pendingRequests.filter((r) => r.id !== requestId);
      const nextAllowed =
        persistDomain && !state.allowedDomains.includes(target.domain)
          ? [...state.allowedDomains, target.domain]
          : state.allowedDomains;

      return {
        pendingRequests: nextPending,
        allowedDomains: nextAllowed,
      };
    });

    get().addAuditLog(
      'egress-allowed',
      `User approved egress to ${target.domain}${persistDomain ? ' (domain whitelisted)' : ''}`,
      target.domain
    );
  },

  denyRequest: (requestId: string) => {
    const target = get().pendingRequests.find((r) => r.id === requestId);
    if (!target) {
      return;
    }

    set((state) => ({
      pendingRequests: state.pendingRequests.filter((r) => r.id !== requestId),
    }));

    get().addAuditLog(
      'egress-denied',
      `User denied egress request to ${target.domain}`,
      target.domain
    );
  },

  addAuditLog: (type: CanvasAuditEventType, detail: string, domain?: string) => {
    const newLog: CanvasSecurityAuditEvent = {
      id: `audit_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      type,
      detail,
      timestamp: Date.now(),
      domain,
    };

    set((state) => ({
      auditLogs: [newLog, ...state.auditLogs].slice(0, 50),
    }));
  },

  clearAuditLogs: () => {
    set({ auditLogs: [] });
  },

  reset: () => {
    set({
      allowedDomains: [],
      pendingRequests: [],
      auditLogs: [],
    });
  },
}));
