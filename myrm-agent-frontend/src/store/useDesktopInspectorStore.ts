import { create } from 'zustand';
import { apiRequest } from '@/lib/api';
import type { BrowserRefInfo } from '@/store/chat/types';

type InspectorMode = 'view' | 'inspect';

interface DesktopViewData {
  screenshotBase64: string;
  mimeType: string;
  refs: Record<string, BrowserRefInfo>;
  appName: string;
  windowTitle: string;
  scope: string;
  needsPermission: boolean;
  viewportWidth: number;
  viewportHeight: number;
  updatedAt: number;
}

interface SelectedElement {
  refId: string;
  info: BrowserRefInfo;
}

interface DesktopInspectorState {
  isOpen: boolean;
  mode: InspectorMode;
  viewData: DesktopViewData | null;
  selectedElement: SelectedElement | null;
  isDesktopActive: boolean;
  instructionText: string;
  isSnapshotLoading: boolean;

  openPanel: () => void;
  closePanel: () => void;
  togglePanel: () => void;
  setMode: (mode: InspectorMode) => void;
  updateViewData: (data: DesktopViewData) => void;
  selectElement: (refId: string, info: BrowserRefInfo) => void;
  clearSelection: () => void;
  setDesktopActive: (active: boolean) => void;
  setInstructionText: (text: string) => void;
  fetchSnapshot: () => Promise<void>;
  reset: () => void;
}

interface DesktopSnapshotResponse {
  screenshot_base64: string;
  mime_type: string;
  refs: Record<string, BrowserRefInfo>;
  app_name: string;
  window_title: string;
  scope: string;
  needs_permission: boolean;
  viewport_width: number;
  viewport_height: number;
}

const useDesktopInspectorStore = create<DesktopInspectorState>((set, get) => ({
  isOpen: false,
  mode: 'view',
  viewData: null,
  selectedElement: null,
  isDesktopActive: false,
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
  setDesktopActive: (active) =>
    set(() => ({
      isDesktopActive: active,
      ...(active ? {} : { isOpen: false, viewData: null, selectedElement: null }),
    })),
  setInstructionText: (text) => set({ instructionText: text }),
  fetchSnapshot: async () => {
    if (get().isSnapshotLoading) return;
    set({ isSnapshotLoading: true });
    try {
      const data = await apiRequest<DesktopSnapshotResponse>('/webui/desktop/snapshot', {
        silent: true,
      });
      set({
        isDesktopActive: true,
        viewData: {
          screenshotBase64: data.screenshot_base64,
          mimeType: data.mime_type,
          refs: data.refs,
          appName: data.app_name,
          windowTitle: data.window_title,
          scope: data.scope,
          needsPermission: data.needs_permission,
          viewportWidth: data.viewport_width,
          viewportHeight: data.viewport_height,
          updatedAt: Date.now(),
        },
      });
    } catch {
      // Snapshot not available — desktop session might not be active
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
      isDesktopActive: false,
      instructionText: '',
      isSnapshotLoading: false,
    }),
}));

export default useDesktopInspectorStore;
