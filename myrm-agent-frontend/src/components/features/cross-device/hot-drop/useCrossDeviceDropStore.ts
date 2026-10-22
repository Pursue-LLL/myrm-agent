/**
 * Cross-Device Hot-Drop Store (Zustand)
 * 跨设备近场零摩擦素材直投与无线外设相机通道集中式状态总线
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 集中式事件广播与无缝光标热注入支持。
 */

import { create } from 'zustand';
import {
  BeamConnectionState,
  BeamPayload,
  BeamSessionDescriptor,
  BeamTransportMode,
  HotDropInjectionResult,
} from './crossDeviceDropTypes';
import {
  createBeamSession,
  createMockBeamPayload,
} from './beamTransportProtocol';

export interface CrossDeviceDropState {
  activeSession: BeamSessionDescriptor;
  incomingPayloadQueue: BeamPayload[];
  activeIncomingPayload: BeamPayload | null;
  isAnchorPopoverOpen: boolean;
  transferProgressPercent: number;
  injectedHistory: HotDropInjectionResult[];

  // Actions
  initNewSession: (transportMode?: BeamTransportMode) => void;
  setAnchorPopoverOpen: (open: boolean) => void;
  setConnectionState: (state: BeamConnectionState) => void;
  connectDevice: (deviceName: string) => void;
  disconnectDevice: () => void;
  receivePayload: (payload: BeamPayload) => void;
  injectPayloadToTarget: (
    payloadId: string,
    targetInputSelector?: string
  ) => void;
  dismissActivePayload: () => void;
  simulateCameraShootAndBeam: (deviceName?: string) => void;
  resetToDefaults: () => void;
}

export const useCrossDeviceDropStore = create<CrossDeviceDropState>(
  (set, get) => ({
    activeSession: createBeamSession('webrtc'),
    incomingPayloadQueue: [],
    activeIncomingPayload: null,
    isAnchorPopoverOpen: false,
    transferProgressPercent: 0,
    injectedHistory: [],

    initNewSession: (transportMode = 'webrtc') => {
      set({
        activeSession: createBeamSession(transportMode),
        transferProgressPercent: 0,
        activeIncomingPayload: null,
      });
    },

    setAnchorPopoverOpen: (open: boolean) => {
      set({ isAnchorPopoverOpen: open });
    },

    setConnectionState: (connectionState: BeamConnectionState) => {
      set((state) => ({
        activeSession: {
          ...state.activeSession,
          connectionState,
        },
      }));
    },

    connectDevice: (deviceName: string) => {
      set((state) => ({
        activeSession: {
          ...state.activeSession,
          connectedDeviceName: deviceName,
          connectionState: 'connected',
        },
      }));
    },

    disconnectDevice: () => {
      set((state) => ({
        activeSession: {
          ...state.activeSession,
          connectedDeviceName: null,
          connectionState: 'idle',
        },
      }));
    },

    receivePayload: (payload: BeamPayload) => {
      set((state) => ({
        incomingPayloadQueue: [payload, ...state.incomingPayloadQueue],
        activeIncomingPayload: payload,
        transferProgressPercent: 100,
        activeSession: {
          ...state.activeSession,
          connectionState: 'completed',
        },
      }));

      // 全局派发直投接收事件，通知宿主聊天输入框
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('myrm:hot-drop-received', {
            detail: { payload },
          })
        );
      }
    },

    injectPayloadToTarget: (
      payloadId: string,
      targetInputSelector = '#chat-user-input'
    ) => {
      const currentPayload = get().activeIncomingPayload;
      if (!currentPayload || currentPayload.id !== payloadId) {
        return;
      }

      const injectionRecord: HotDropInjectionResult = {
        payloadId,
        injectedAtTimestamp: Date.now(),
        targetInputSelector,
        status: 'injected',
      };

      set((state) => ({
        injectedHistory: [injectionRecord, ...state.injectedHistory],
        activeIncomingPayload: null,
      }));

      // 全局广播光标热注入事件，供输入框光标联动与自动聚焦提示词尾部
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('myrm:hot-drop-injected', {
            detail: {
              payload: currentPayload,
              targetInputSelector,
            },
          })
        );
      }
    },

    dismissActivePayload: () => {
      set({ activeIncomingPayload: null });
    },

    simulateCameraShootAndBeam: (deviceName = 'iPhone 16 Pro') => {
      // 模拟手机拍摄并极速推流
      set((state) => ({
        activeSession: {
          ...state.activeSession,
          connectedDeviceName: deviceName,
          connectionState: 'beaming',
        },
        transferProgressPercent: 45,
      }));

      const mockPayload = createMockBeamPayload(deviceName);

      setTimeout(() => {
        get().receivePayload(mockPayload);
      }, 30);
    },

    resetToDefaults: () => {
      set({
        activeSession: createBeamSession('webrtc'),
        incomingPayloadQueue: [],
        activeIncomingPayload: null,
        isAnchorPopoverOpen: false,
        transferProgressPercent: 0,
        injectedHistory: [],
      });
    },
  })
);
