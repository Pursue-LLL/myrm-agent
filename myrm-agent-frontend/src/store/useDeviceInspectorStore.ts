/**
 * [INPUT]
 * @/store/chat/types::BrowserRefInfo (POS: mobile element reference info with BBox)
 *
 * [OUTPUT]
 * useDeviceInspectorStore: Zustand store for Mobile Device Inspector panel state.
 * selectScopedDeviceViewData: chat-scoped viewData selector for multi-pane SSE isolation.
 *
 * [POS]
 * State management for the Mobile Device Live View + Interactive Inspector feature.
 * Tracks panel visibility, active mode, latest device screen data, touch relay commands,
 * and per-chat turn engagement.
 */

import { create } from 'zustand';
import { apiRequest } from '@/lib/api';
import type { BrowserRefInfo } from '@/store/chat/types';

type InspectorMode = 'view' | 'inspect';

export interface DeviceDoctorInfo {
  adb_installed: boolean;
  adb_path: string | null;
  connected: boolean;
  active_device_serial: string | null;
  diagnostic_message: string;
  remediation_hint: string | null;
  devices_count?: number;
}

export interface DeviceViewData {
  screenshotBase64: string;
  mimeType: string;
  refs: Record<string, BrowserRefInfo>;
  deviceId: string;
  deviceName: string;
  platform: 'android' | 'ios' | 'harmony' | 'generic';
  connected: boolean;
  notificationRedaction: boolean;
  viewportWidth: number;
  viewportHeight: number;
  sourceChatId: string;
  doctor?: DeviceDoctorInfo;
  /** True when produced by an agent turn event (DEVICE_VIEW_UPDATE); false for manual snapshots. */
  isTurnView?: boolean;
  updatedAt: number;
}

/** Return device view data only when it belongs to the active chat (multi-pane SSE isolation). */
export function selectScopedDeviceViewData(
  viewData: DeviceViewData | null,
  chatId: string | null | undefined,
): DeviceViewData | null {
  const normalizedChatId = chatId?.trim() ?? '';
  if (!normalizedChatId || !viewData) {
    return null;
  }
  return viewData.sourceChatId === normalizedChatId ? viewData : null;
}

interface SelectedElement {
  refId: string;
  info: BrowserRefInfo;
}

export interface TouchRelayCommand {
  action: 'tap' | 'swipe' | 'scroll' | 'hold' | 'keyevent';
  x?: number;
  y?: number;
  endX?: number;
  endY?: number;
  durationMs?: number;
  keycode?: string;
  deviceId?: string;
}

interface DeviceInspectorState {
  isOpen: boolean;
  mode: InspectorMode;
  viewData: DeviceViewData | null;
  selectedElement: SelectedElement | null;
  isDeviceActive: boolean;
  notificationRedaction: boolean;
  instructionText: string;
  isSnapshotLoading: boolean;
  engagedChatId: string | null;

  openPanel: () => void;
  closePanel: () => void;
  togglePanel: () => void;
  setMode: (mode: InspectorMode) => void;
  setNotificationRedaction: (enabled: boolean) => void;
  updateViewData: (data: DeviceViewData) => void;
  selectElement: (refId: string, info: BrowserRefInfo) => void;
  clearSelection: () => void;
  setDeviceActive: (active: boolean) => void;
  markTurnEngaged: (chatId: string) => void;
  releaseTurnEngagement: (chatId: string) => void;
  setInstructionText: (text: string) => void;
  sendTouchRelay: (command: TouchRelayCommand) => Promise<boolean>;
  fetchSnapshot: (isTurnView?: boolean, targetDeviceId?: string) => Promise<boolean>;
  reset: () => void;
}

interface DeviceSnapshotResponse {
  screenshot_base64: string;
  mime_type: string;
  refs: Record<string, BrowserRefInfo>;
  device_id: string;
  device_name: string;
  platform: 'android' | 'ios' | 'harmony' | 'generic';
  connected: boolean;
  viewport_width: number;
  viewport_height: number;
  doctor?: DeviceDoctorInfo;
}

const useDeviceInspectorStore = create<DeviceInspectorState>((set, get) => ({
  isOpen: false,
  mode: 'view',
  viewData: null,
  selectedElement: null,
  isDeviceActive: false,
  notificationRedaction: true,
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
  setNotificationRedaction: (enabled) => set({ notificationRedaction: enabled }),
  updateViewData: (data) => set({ viewData: data }),
  selectElement: (refId, info) => set({ selectedElement: { refId, info } }),
  clearSelection: () => set({ selectedElement: null }),
  setDeviceActive: (active) => set({ isDeviceActive: active }),
  markTurnEngaged: (chatId) => {
    if (chatId) {
      set({ engagedChatId: chatId });
    }
  },
  releaseTurnEngagement: (chatId) => {
    const { engagedChatId, viewData } = get();
    const shouldReclaimView = viewData?.isTurnView && viewData.sourceChatId === chatId;
    if (engagedChatId === chatId) {
      set({
        engagedChatId: null,
        ...(shouldReclaimView ? { viewData: null, selectedElement: null } : {}),
      });
    } else if (shouldReclaimView) {
      set({ viewData: null, selectedElement: null });
    }
  },
  setInstructionText: (text) => set({ instructionText: text }),

  sendTouchRelay: async (command: TouchRelayCommand) => {
    try {
      await apiRequest('/webui/device/relay', {
        method: 'POST',
        body: JSON.stringify(command),
        silent: true,
      });
      return true;
    } catch {
      return false;
    }
  },

  fetchSnapshot: async (isTurnView = false, targetDeviceId?: string) => {
    set({ isSnapshotLoading: true });
    try {
      const { default: useChatStore } = await import('@/store/useChatStore');
      const activeChatId = useChatStore.getState().chatId?.trim() ?? '';
      const params = new URLSearchParams();
      if (activeChatId) {
        params.set('chat_id', activeChatId);
      }
      params.set('redact_notifications', String(get().notificationRedaction));
      if (targetDeviceId) {
        params.set('device_id', targetDeviceId);
      }

      const queryStr = params.toString() ? `?${params.toString()}` : '';
      const data = await apiRequest<DeviceSnapshotResponse>(`/webui/device/snapshot${queryStr}`, {
        silent: true,
      });

      const viewData: DeviceViewData = {
        screenshotBase64: data.screenshot_base64,
        mimeType: data.mime_type || 'image/png',
        refs: data.refs || {},
        deviceId: data.device_id || 'default_device',
        deviceName: data.device_name || 'Mobile Device',
        platform: data.platform || 'android',
        connected: data.connected ?? true,
        notificationRedaction: get().notificationRedaction,
        viewportWidth: data.viewport_width || 1080,
        viewportHeight: data.viewport_height || 2400,
        sourceChatId: activeChatId,
        doctor: data.doctor,
        isTurnView,
        updatedAt: Date.now(),
      };
      set({ viewData, isDeviceActive: true });
      return true;
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
      isDeviceActive: false,
      notificationRedaction: true,
      instructionText: '',
      isSnapshotLoading: false,
      engagedChatId: null,
    }),
}));

if (typeof window !== 'undefined') {
  (window as unknown as { __MYRM_DEVICE_INSPECTOR_STORE__?: typeof useDeviceInspectorStore }).__MYRM_DEVICE_INSPECTOR_STORE__ =
    useDeviceInspectorStore;
}

export default useDeviceInspectorStore;
