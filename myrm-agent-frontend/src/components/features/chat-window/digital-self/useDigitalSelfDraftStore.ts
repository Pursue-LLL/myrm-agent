/**
 * [INPUT]
 * - digitalSelfTypes::DigitalSelfDraftItem, OutboundAuditRecord, ToneStyle (POS: Digital self contract.)
 * - zustand::create (POS: Reactive state management.)
 *
 * [OUTPUT]
 * - useDigitalSelfDraftStore: hook managing tone draft queue, inline edits, and outbound hard gate.
 *
 * [POS]
 * Controls the digital self persona drafting queue and enforces the physical
 * outbound confirmation gate, guaranteeing no outbound messages leak without human consent.
 */

import { create } from 'zustand';
import type {
  DigitalSelfDraftItem,
  OutboundAuditRecord,
  ToneStyle,
} from './digitalSelfTypes';

const STORAGE_KEY = 'myrm_digital_self_drafts';
const AUDIT_STORAGE_KEY = 'myrm_digital_self_audit_log';

interface DigitalSelfDraftState {
  drafts: DigitalSelfDraftItem[];
  auditLog: OutboundAuditRecord[];
  addDraft: (
    item: Omit<DigitalSelfDraftItem, 'id' | 'createdAt' | 'status' | 'explicitlyConfirmedByHuman'>,
  ) => string;
  updateDraftContent: (draftId: string, content: string) => void;
  changeToneStyle: (draftId: string, toneStyle: ToneStyle) => void;
  confirmAndSendOutbound: (draftId: string) => Promise<{ success: boolean; error?: string }>;
  discardDraft: (draftId: string) => void;
  clearCompleted: () => void;
}

function loadPersistedDrafts(): DigitalSelfDraftItem[] {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed;
      }
    }
  } catch {
    // Ignore localStorage parse error
  }
  return [];
}

function loadPersistedAuditLog(): OutboundAuditRecord[] {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    const raw = localStorage.getItem(AUDIT_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed;
      }
    }
  } catch {
    // Ignore localStorage parse error
  }
  return [];
}

function persistDrafts(drafts: DigitalSelfDraftItem[]): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(drafts));
  } catch {
    // Ignore storage failure
  }
}

function persistAuditLog(log: OutboundAuditRecord[]): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    localStorage.setItem(AUDIT_STORAGE_KEY, JSON.stringify(log));
  } catch {
    // Ignore storage failure
  }
}

export const useDigitalSelfDraftStore = create<DigitalSelfDraftState>((set, get) => ({
  drafts: loadPersistedDrafts(),
  auditLog: loadPersistedAuditLog(),

  addDraft: (item) => {
    const id = `draft_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    const newDraft: DigitalSelfDraftItem = {
      ...item,
      id,
      createdAt: Date.now(),
      status: 'pending_review',
      explicitlyConfirmedByHuman: false,
    };
    const nextDrafts = [newDraft, ...get().drafts];
    persistDrafts(nextDrafts);
    set({ drafts: nextDrafts });
    return id;
  },

  updateDraftContent: (draftId, content) => {
    const nextDrafts = get().drafts.map((d) => {
      if (d.id !== draftId) {
        return d;
      }
      return {
        ...d,
        draftContent: content,
        status: d.status === 'confirmed_sent' ? d.status : ('edited' as const),
      };
    });
    persistDrafts(nextDrafts);
    set({ drafts: nextDrafts });
  },

  changeToneStyle: (draftId, toneStyle) => {
    const nextDrafts = get().drafts.map((d) => {
      if (d.id !== draftId) {
        return d;
      }
      return {
        ...d,
        toneStyle,
        status: d.status === 'confirmed_sent' ? d.status : ('edited' as const),
      };
    });
    persistDrafts(nextDrafts);
    set({ drafts: nextDrafts });
  },

  confirmAndSendOutbound: async (draftId) => {
    const targetDraft = get().drafts.find((d) => d.id === draftId);
    if (!targetDraft) {
      return { success: false, error: 'Draft not found.' };
    }

    if (targetDraft.status === 'confirmed_sent') {
      return { success: false, error: 'Draft has already been sent.' };
    }

    const now = Date.now();
    const auditRecord: OutboundAuditRecord = {
      recordId: `audit_${now}_${Math.random().toString(36).slice(2, 7)}`,
      draftId,
      channel: targetDraft.channel,
      recipientName: targetDraft.recipientName,
      finalContent: targetDraft.draftContent,
      sentAt: now,
      confirmedByHuman: true,
    };

    const nextDrafts = get().drafts.map((d) => {
      if (d.id !== draftId) {
        return d;
      }
      return {
        ...d,
        status: 'confirmed_sent' as const,
        confirmedAt: now,
        explicitlyConfirmedByHuman: true,
      };
    });

    const nextAudit = [auditRecord, ...get().auditLog];
    persistDrafts(nextDrafts);
    persistAuditLog(nextAudit);

    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('myrm:outbound-message-sent', {
          detail: { draftId, channel: targetDraft.channel, sentAt: now },
        }),
      );
    }

    set({ drafts: nextDrafts, auditLog: nextAudit });
    return { success: true };
  },

  discardDraft: (draftId) => {
    const nextDrafts = get().drafts.map((d) => {
      if (d.id !== draftId) {
        return d;
      }
      return {
        ...d,
        status: 'discarded' as const,
      };
    });
    persistDrafts(nextDrafts);
    set({ drafts: nextDrafts });
  },

  clearCompleted: () => {
    const nextDrafts = get().drafts.filter(
      (d) => d.status === 'pending_review' || d.status === 'edited',
    );
    persistDrafts(nextDrafts);
    set({ drafts: nextDrafts });
  },
}));
