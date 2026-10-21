import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useCrossDeviceDropStore } from '../useCrossDeviceDropStore';
import { createMockBeamPayload } from '../beamTransportProtocol';

describe('useCrossDeviceDropStore', () => {
  beforeEach(() => {
    useCrossDeviceDropStore.getState().resetToDefaults();
    vi.restoreAllMocks();
  });

  it('初始状态具备默认会话描述符与空队列', () => {
    const state = useCrossDeviceDropStore.getState();
    expect(state.activeSession.connectionState).toBe('idle');
    expect(state.activeSession.connectedDeviceName).toBeNull();
    expect(state.incomingPayloadQueue).toHaveLength(0);
    expect(state.activeIncomingPayload).toBeNull();
    expect(state.isAnchorPopoverOpen).toBe(false);
  });

  it('连接与断开设备能够正确更新状态与设备名称', () => {
    useCrossDeviceDropStore.getState().connectDevice('iPhone 16 Pro Max');

    let state = useCrossDeviceDropStore.getState();
    expect(state.activeSession.connectedDeviceName).toBe('iPhone 16 Pro Max');
    expect(state.activeSession.connectionState).toBe('connected');

    useCrossDeviceDropStore.getState().disconnectDevice();
    state = useCrossDeviceDropStore.getState();
    expect(state.activeSession.connectedDeviceName).toBeNull();
    expect(state.activeSession.connectionState).toBe('idle');
  });

  it('接收投送载荷能够入队并派发全局 myrm:hot-drop-received 事件', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const mockPayload = createMockBeamPayload('iPad Pro', '分析表格');

    useCrossDeviceDropStore.getState().receivePayload(mockPayload);

    const state = useCrossDeviceDropStore.getState();
    expect(state.incomingPayloadQueue).toHaveLength(1);
    expect(state.activeIncomingPayload).toEqual(mockPayload);
    expect(state.activeSession.connectionState).toBe('completed');

    expect(dispatchSpy).toHaveBeenCalled();
    const event = dispatchSpy.mock.calls.find(
      (call) => (call[0] as CustomEvent).type === 'myrm:hot-drop-received'
    );
    expect(event).toBeDefined();
    if (event) {
      const customEvent = event[0] as CustomEvent;
      expect(customEvent.detail.payload.sourceDeviceName).toBe('iPad Pro');
    }
  });

  it('确认注入能够记录历史并派发 myrm:hot-drop-injected 事件', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const mockPayload = createMockBeamPayload('Pixel 9 Pro');

    useCrossDeviceDropStore.getState().receivePayload(mockPayload);
    useCrossDeviceDropStore
      .getState()
      .injectPayloadToTarget(mockPayload.id, '#custom-input');

    const state = useCrossDeviceDropStore.getState();
    expect(state.activeIncomingPayload).toBeNull();
    expect(state.injectedHistory).toHaveLength(1);
    expect(state.injectedHistory[0]).toEqual(
      expect.objectContaining({
        payloadId: mockPayload.id,
        targetInputSelector: '#custom-input',
        status: 'injected',
      })
    );

    const event = dispatchSpy.mock.calls.find(
      (call) => (call[0] as CustomEvent).type === 'myrm:hot-drop-injected'
    );
    expect(event).toBeDefined();
  });

  it('忽略当前素材能够清空 activeIncomingPayload', () => {
    const mockPayload = createMockBeamPayload();
    useCrossDeviceDropStore.getState().receivePayload(mockPayload);
    expect(useCrossDeviceDropStore.getState().activeIncomingPayload).toBeDefined();

    useCrossDeviceDropStore.getState().dismissActivePayload();
    expect(useCrossDeviceDropStore.getState().activeIncomingPayload).toBeNull();
  });

  it('模拟手机拍照并推流能够异步完成接收流程', async () => {
    vi.useFakeTimers();

    useCrossDeviceDropStore.getState().simulateCameraShootAndBeam('Huawei Mate 60');

    expect(
      useCrossDeviceDropStore.getState().activeSession.connectionState
    ).toBe('beaming');
    expect(
      useCrossDeviceDropStore.getState().activeSession.connectedDeviceName
    ).toBe('Huawei Mate 60');

    vi.advanceTimersByTime(50);

    expect(
      useCrossDeviceDropStore.getState().activeSession.connectionState
    ).toBe('completed');
    expect(
      useCrossDeviceDropStore.getState().activeIncomingPayload
    ).toBeDefined();

    vi.useRealTimers();
  });
});
