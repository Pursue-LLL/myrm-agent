/**
 * [INPUT]
 * @/store/chat/types::BrowserRefInfo (POS: Browser element reference info with BBox)
 *
 * [OUTPUT]
 * useBrowserInspectorStore: Zustand store for Browser Inspector panel state.
 *
 * [POS]
 * State management for the Browser Live View + Interactive Inspector feature.
 * Tracks panel visibility, active mode, latest browser view data, and selected element.
 */

import { create } from 'zustand';
import { apiRequest } from '@/lib/api';
import type { BrowserRefInfo } from '@/store/chat/types';

type InspectorMode = 'view' | 'inspect';

interface BrowserViewData {
  screenshotBase64: string;
  mimeType: string;
  refs: Record<string, BrowserRefInfo>;
  pageUrl: string;
  pageTitle: string;
  viewportWidth: number;
  viewportHeight: number;
  updatedAt: number;
}

interface BrowserSnapshotResponse {
  screenshot_base64: string;
  mime_type: string;
  refs: Record<string, BrowserRefInfo>;
  page_url: string;
  page_title: string;
  viewport_width: number;
  viewport_height: number;
}

interface SelectedElement {
  refId: string;
  info: BrowserRefInfo;
}

interface BrowserInspectorState {
  isOpen: boolean;
  mode: InspectorMode;
  viewData: BrowserViewData | null;
  selectedElement: SelectedElement | null;
  isBrowserActive: boolean;
  instructionText: string;
  isSnapshotLoading: boolean;

  openPanel: () => void;
  closePanel: () => void;
  togglePanel: () => void;
  setMode: (mode: InspectorMode) => void;
  updateViewData: (data: BrowserViewData) => void;
  selectElement: (refId: string, info: BrowserRefInfo) => void;
  clearSelection: () => void;
  setBrowserActive: (active: boolean) => void;
  setInstructionText: (text: string) => void;
  fetchSnapshot: () => Promise<void>;
  reset: () => void;
}

const useBrowserInspectorStore = create<BrowserInspectorState>((set, get) => ({
  isOpen: false,
  mode: 'view',
  viewData: null,
  selectedElement: null,
  isBrowserActive: false,
  instructionText: '',
  isSnapshotLoading: false,

  openPanel: () => set({ isOpen: true }),
  closePanel: () => set({ isOpen: false, selectedElement: null, instructionText: '' }),
  togglePanel: () =>
    set((s) => ({
      isOpen: !s.isOpen,
      ...(s.isOpen ? { selectedElement: null, instructionText: '' } : {}),
    })),
  setMode: (mode) => set({ mode, selectedElement: null }),
  updateViewData: (data) => set({ viewData: data }),
  selectElement: (refId, info) => set({ selectedElement: { refId, info } }),
  clearSelection: () => set({ selectedElement: null }),
  setBrowserActive: (active) =>
    set((_s) => ({
      isBrowserActive: active,
      ...(active ? {} : { isOpen: false, viewData: null, selectedElement: null }),
    })),
  setInstructionText: (text) => set({ instructionText: text }),
  fetchSnapshot: async () => {
    if (get().isSnapshotLoading) return;
    set({ isSnapshotLoading: true });
    try {
      const data = await apiRequest<BrowserSnapshotResponse>('/webui/browser/snapshot', {
        silent: true,
      });
      set({
        isBrowserActive: true,
        viewData: {
          screenshotBase64: data.screenshot_base64,
          mimeType: data.mime_type,
          refs: data.refs,
          pageUrl: data.page_url,
          pageTitle: data.page_title,
          viewportWidth: data.viewport_width,
          viewportHeight: data.viewport_height,
          updatedAt: Date.now(),
        },
      });
    } catch {
      // Snapshot not available — browser might not be active
    } finally {
      set({ isSnapshotLoading: false });
    }
  },
  reset: () =>
    set({
      isOpen: false,
      mode: 'view',
      viewData: null,
      selectedElement: null,
      isBrowserActive: false,
      instructionText: '',
      isSnapshotLoading: false,
    }),
}));

export default useBrowserInspectorStore;
