/**
 * [INPUT]
 * @/store/chat/types::BrowserRefInfo (POS: Browser element reference info with BBox)
 *
 * [OUTPUT]
 * useBrowserInspectorStore: Zustand store for Browser Inspector panel state.
 * selectScopedBrowserViewData: chat-scoped viewData selector for multi-pane SSE isolation.
 *
 * [POS]
 * State management for the Browser Live View + Interactive Inspector feature.
 * Tracks panel visibility, active mode, latest browser view data, selected element, and
 * per-chat turn engagement (which chat's turn drives browser events and must be torn down;
 * release reclaims the view owned by the ending turn even if its engagement slot was
 * overwritten by another pane, and keeps viewData owned by another chat / a manually
 * opened panel (isTurnView=false) untouched, so parallel panes are never force-closed).
 */

import { create } from 'zustand';
import { apiRequest } from '@/lib/api';
import type { BrowserRefInfo } from '@/store/chat/types';

type InspectorMode = 'view' | 'inspect';

export interface BrowserViewData {
  screenshotBase64: string;
  mimeType: string;
  refs: Record<string, BrowserRefInfo>;
  pageUrl: string;
  pageTitle: string;
  viewportWidth: number;
  viewportHeight: number;
  sourceChatId: string;
  /** True when produced by an agent turn event (BROWSER_VIEW_UPDATE); false for manual snapshots (fetchSnapshot). */
  isTurnView?: boolean;
  updatedAt: number;
}

/** Return browser view data only when it belongs to the active chat (multi-pane SSE isolation). */
export function selectScopedBrowserViewData(
  viewData: BrowserViewData | null,
  chatId: string | null | undefined,
): BrowserViewData | null {
  const normalizedChatId = chatId?.trim() ?? '';
  if (!normalizedChatId || !viewData) {
    return null;
  }
  return viewData.sourceChatId === normalizedChatId ? viewData : null;
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
  /** Chat id of the turn currently emitting browser events; null when no turn is engaged. */
  engagedChatId: string | null;

  openPanel: () => void;
  closePanel: () => void;
  togglePanel: () => void;
  setMode: (mode: InspectorMode) => void;
  updateViewData: (data: BrowserViewData) => void;
  selectElement: (refId: string, info: BrowserRefInfo) => void;
  clearSelection: () => void;
  setBrowserActive: (active: boolean) => void;
  markTurnEngaged: (chatId: string) => void;
  releaseTurnEngagement: (chatId: string) => void;
  setInstructionText: (text: string) => void;
  fetchSnapshot: (isTurnView?: boolean) => Promise<boolean>;
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
  engagedChatId: null,

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
  markTurnEngaged: (chatId) => {
    if (!chatId) {return;}
    set({ engagedChatId: chatId });
  },
  releaseTurnEngagement: (chatId) =>
    set((s) => {
      const ownsEngagement = s.engagedChatId === chatId;
      const viewBelongsToTurn =
        s.viewData !== null && s.viewData.isTurnView === true && s.viewData.sourceChatId === chatId;
      if (!ownsEngagement && !viewBelongsToTurn) {
        // Unrelated turn / manually opened panel / already released: return the same
        // reference so zustand skips the subscription notify on a no-op.
        return s;
      }
      if (s.viewData !== null && (s.viewData.isTurnView !== true || s.viewData.sourceChatId !== chatId)) {
        // A manual snapshot (isTurnView=false) belongs to the user, or the view belongs
        // to another turn that is still controlling: only return our ownership, keep the
        // view, active flag and panel untouched.
        return { engagedChatId: null };
      }
      // This turn owns the view (or engaged with no view at all): full teardown.
      return {
        engagedChatId: null,
        isBrowserActive: false,
        isOpen: false,
        viewData: null,
        selectedElement: null,
        instructionText: '',
      };
    }),
  setInstructionText: (text) => set({ instructionText: text }),
  fetchSnapshot: async (isTurnView = false) => {
    if (get().isSnapshotLoading) {return false;}
    const { default: useChatStore } = await import('@/store/useChatStore');
    const chatId = useChatStore.getState().chatId?.trim();
    if (!chatId) {return false;}
    set({ isSnapshotLoading: true });
    try {
      const data = await apiRequest<BrowserSnapshotResponse>(
        `/webui/browser/snapshot?chat_id=${encodeURIComponent(chatId)}`,
        {
          silent: true,
        },
      );
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
          sourceChatId: chatId,
          isTurnView,
          updatedAt: Date.now(),
        },
      });
      return Boolean(data.screenshot_base64);
    } catch {
      return false;
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
      engagedChatId: null,
    }),
}));

export default useBrowserInspectorStore;
