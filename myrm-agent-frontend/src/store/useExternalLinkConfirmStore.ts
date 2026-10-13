'use client';

import { create } from 'zustand';

/** An external link requested by embedded third-party content, waiting for the user's decision. */
export interface PendingExternalLink {
  /** Normalized http(s) address that will be opened on approval. */
  url: string;
  /** Name of the app that asked for the link; null when the host cannot attribute the request. */
  source: string | null;
}

/** Requests arriving this soon after a refusal are dropped, so hostile content cannot re-prompt in a loop. */
export const DECLINE_QUIET_PERIOD_MS = 2000;

interface ExternalLinkConfirmState {
  open: boolean;
  /** Kept after closing so the dialog finishes its exit animation with the same content. */
  link: PendingExternalLink | null;
  /** Epoch ms of the last refusal. */
  declinedAt: number;
  /** Shows the prompt unless one is already open (single-flight) or the user has just declined. */
  request: (link: PendingExternalLink) => void;
  approve: () => void;
  /** Refuses the open prompt; a no-op when none is open, so the dialog's close callback can call it unconditionally. */
  decline: () => void;
}

export const useExternalLinkConfirmStore = create<ExternalLinkConfirmState>((set, get) => ({
  open: false,
  link: null,
  declinedAt: 0,

  request: (link) => {
    const { open, declinedAt } = get();
    // A negative age means the wall clock stepped back after the refusal; treating it as quiet would
    // swallow every request until the clock catches up, so only a non-negative age counts.
    const sinceDecline = Date.now() - declinedAt;
    if (open || (sinceDecline >= 0 && sinceDecline < DECLINE_QUIET_PERIOD_MS)) {
      return;
    }
    set({ open: true, link });
  },

  approve: () => set({ open: false }),

  decline: () => {
    if (get().open) {
      set({ open: false, declinedAt: Date.now() });
    }
  },
}));
