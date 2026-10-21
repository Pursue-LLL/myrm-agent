import { create } from 'zustand';
import { AuditCitationItem, SearchAuditSession } from './searchAuditTypes';

export type SearchAuditTab = 'waterfall' | 'quality_matrix' | 'evidence_compare';

export interface SearchAuditStoreState {
  isDrawerOpen: boolean;
  activeSession: SearchAuditSession | null;
  selectedCitation: AuditCitationItem | null;
  activeTab: SearchAuditTab;

  // Actions
  openAuditDrawer: (
    session: SearchAuditSession,
    initialCitationId?: string
  ) => void;
  closeAuditDrawer: () => void;
  toggleAuditDrawer: (open?: boolean) => void;
  selectCitation: (citation: AuditCitationItem | null) => void;
  setActiveTab: (tab: SearchAuditTab) => void;
  clearSession: () => void;
}

export const useSearchAuditStore = create<SearchAuditStoreState>((set) => ({
  isDrawerOpen: false,
  activeSession: null,
  selectedCitation: null,
  activeTab: 'waterfall',

  openAuditDrawer: (
    session: SearchAuditSession,
    initialCitationId?: string
  ) => {
    let initialCitation = session.citations.length > 0 ? session.citations[0] : null;
    if (initialCitationId) {
      const found = session.citations.find((c) => c.id === initialCitationId);
      if (found) {
        initialCitation = found;
      }
    }

    set({
      activeSession: session,
      selectedCitation: initialCitation,
      isDrawerOpen: true,
      activeTab: initialCitationId ? 'evidence_compare' : 'waterfall',
    });
  },

  closeAuditDrawer: () => {
    set({ isDrawerOpen: false });
  },

  toggleAuditDrawer: (open?: boolean) => {
    set((state) => ({
      isDrawerOpen: typeof open === 'boolean' ? open : !state.isDrawerOpen,
    }));
  },

  selectCitation: (citation: AuditCitationItem | null) => {
    set({ selectedCitation: citation });
  },

  setActiveTab: (tab: SearchAuditTab) => {
    set({ activeTab: tab });
  },

  clearSession: () => {
    set({
      activeSession: null,
      selectedCitation: null,
      isDrawerOpen: false,
      activeTab: 'waterfall',
    });
  },
}));
