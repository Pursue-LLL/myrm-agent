import { describe, it, expect, beforeEach } from 'vitest';
import useDeviceInspectorStore, {
  selectScopedDeviceViewData,
  type DeviceViewData,
} from '../useDeviceInspectorStore';

describe('useDeviceInspectorStore & selectScopedDeviceViewData', () => {
  beforeEach(() => {
    useDeviceInspectorStore.getState().reset();
  });

  it('selectScopedDeviceViewData returns viewData only when chatId matches', () => {
    const mockData: DeviceViewData = {
      screenshotBase64: 'abc',
      mimeType: 'image/png',
      refs: {},
      deviceId: 'device-1',
      deviceName: 'Test Phone',
      platform: 'android',
      connected: true,
      notificationRedaction: true,
      viewportWidth: 1080,
      viewportHeight: 2400,
      sourceChatId: 'chat-123',
      updatedAt: 1000,
    };

    expect(selectScopedDeviceViewData(mockData, 'chat-123')).toEqual(mockData);
    expect(selectScopedDeviceViewData(mockData, 'chat-456')).toBeNull();
    expect(selectScopedDeviceViewData(mockData, '')).toBeNull();
    expect(selectScopedDeviceViewData(null, 'chat-123')).toBeNull();
  });

  it('toggles panel and updates mode', () => {
    const store = useDeviceInspectorStore.getState();
    expect(store.isOpen).toBe(false);

    store.togglePanel();
    expect(useDeviceInspectorStore.getState().isOpen).toBe(true);

    store.setMode('inspect');
    expect(useDeviceInspectorStore.getState().mode).toBe('inspect');

    store.setNotificationRedaction(false);
    expect(useDeviceInspectorStore.getState().notificationRedaction).toBe(false);

    store.closePanel();
    expect(useDeviceInspectorStore.getState().isOpen).toBe(false);
  });

  it('handles per-chat turn engagement and release', () => {
    const store = useDeviceInspectorStore.getState();

    store.markTurnEngaged('chat-1');
    expect(useDeviceInspectorStore.getState().engagedChatId).toBe('chat-1');

    store.updateViewData({
      screenshotBase64: 'base64',
      mimeType: 'image/png',
      refs: {},
      deviceId: 'dev-1',
      deviceName: 'Pixel',
      platform: 'android',
      connected: true,
      notificationRedaction: true,
      viewportWidth: 1080,
      viewportHeight: 2400,
      sourceChatId: 'chat-1',
      isTurnView: true,
      updatedAt: Date.now(),
    });

    store.releaseTurnEngagement('chat-1');
    expect(useDeviceInspectorStore.getState().engagedChatId).toBeNull();
    expect(useDeviceInspectorStore.getState().viewData).toBeNull();
  });
});
