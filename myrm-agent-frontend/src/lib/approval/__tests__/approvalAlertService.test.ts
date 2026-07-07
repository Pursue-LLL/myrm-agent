import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/tauri', () => ({
  isTauriEnvironment: vi.fn(() => false),
}));

vi.mock('@/services/config', () => ({
  getConfigSyncManager: vi.fn(() => ({
    get: vi.fn(() => ({
      enableIdleApprovalNotification: true,
      approvalNotificationSound: true,
    })),
  })),
}));

import { notifyIdleApproval, closeNotification, clearAllNotifications } from '../approvalAlertService';
import { isTauriEnvironment } from '@/lib/tauri';
import { getConfigSyncManager } from '@/services/config';
import type { ToolApprovalRequest } from '@/store/chat/types';

function makeRequest(overrides: Partial<ToolApprovalRequest> = {}): ToolApprovalRequest {
  return {
    requestId: 'req-1',
    toolName: 'file_write_tool',
    toolInput: {},
    reason: 'Write to important file',
    timeoutSeconds: 60,
    expiresAt: Math.floor(Date.now() / 1000) + 60,
    timeoutBehavior: 'deny',
    messageId: 'msg-1',
    displayMode: 'approval',
    chatId: 'chat-1',
    actionMode: 'agent',
    ...overrides,
  };
}

class MockNotification {
  static permission = 'granted';
  static requestPermission = vi.fn(() => Promise.resolve('granted' as NotificationPermission));
  body: string;
  tag: string;
  requireInteraction: boolean;
  onclick: (() => void) | null = null;
  close = vi.fn();

  constructor(title: string, options?: NotificationOptions) {
    this.body = options?.body ?? '';
    this.tag = options?.tag ?? '';
    this.requireInteraction = options?.requireInteraction ?? false;
    mockNotificationInstances.push(this);
  }
}

let mockNotificationInstances: MockNotification[] = [];

describe('approvalAlertService', () => {
  let originalHidden: boolean;

  beforeEach(() => {
    vi.useFakeTimers();
    mockNotificationInstances = [];
    originalHidden = document.hidden;
    Object.defineProperty(document, 'hidden', { value: true, writable: true, configurable: true });
    Object.defineProperty(window, 'Notification', { value: MockNotification, writable: true, configurable: true });
    localStorage.clear();
    vi.mocked(isTauriEnvironment).mockReturnValue(false);
    vi.mocked(getConfigSyncManager).mockReturnValue({
      get: vi.fn(() => ({
        enableIdleApprovalNotification: true,
        approvalNotificationSound: true,
      })),
    } as ReturnType<typeof getConfigSyncManager>);
  });

  afterEach(() => {
    clearAllNotifications();
    Object.defineProperty(document, 'hidden', { value: originalHidden, configurable: true });
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  describe('notifyIdleApproval', () => {
    it('does nothing when page is visible', () => {
      Object.defineProperty(document, 'hidden', { value: false, configurable: true });
      notifyIdleApproval([makeRequest()]);
      expect(mockNotificationInstances).toHaveLength(0);
    });

    it('does nothing when disabled via config', () => {
      vi.mocked(getConfigSyncManager).mockReturnValue({
        get: vi.fn(() => ({
          enableIdleApprovalNotification: false,
          approvalNotificationSound: true,
        })),
      } as ReturnType<typeof getConfigSyncManager>);
      notifyIdleApproval([makeRequest()]);
      expect(mockNotificationInstances).toHaveLength(0);
    });

    it('does nothing with empty requests array', () => {
      notifyIdleApproval([]);
      expect(mockNotificationInstances).toHaveLength(0);
    });

    it('sends browser notification for single request', () => {
      notifyIdleApproval([makeRequest()]);
      expect(mockNotificationInstances).toHaveLength(1);
    });

    it('batches requests by batchId', () => {
      const requests = [
        makeRequest({ requestId: 'r1', batchId: 'batch-a' }),
        makeRequest({ requestId: 'r2', batchId: 'batch-a' }),
        makeRequest({ requestId: 'r3' }),
      ];
      notifyIdleApproval(requests);
      // batch-a group + r3 individual = 2 notifications
      expect(mockNotificationInstances).toHaveLength(2);
    });

    it('starts title flash when page is hidden', () => {
      const originalTitle = document.title;
      notifyIdleApproval([makeRequest()]);
      vi.advanceTimersByTime(1000);
      expect(document.title).not.toBe(originalTitle);
      clearAllNotifications();
      expect(document.title).toBe(originalTitle);
    });

    it('respects MAX_ACTIVE_NOTIFICATIONS limit (5)', () => {
      for (let i = 0; i < 8; i++) {
        notifyIdleApproval([makeRequest({ requestId: `req-${i}` })]);
      }
      // Should have created 8 notifications but pruned down to 5 active
      const closedCount = mockNotificationInstances.filter((n) => n.close.mock.calls.length > 0).length;
      expect(closedCount).toBe(3);
    });

    it('requests notification permission when status is default', () => {
      MockNotification.permission = 'default';
      notifyIdleApproval([makeRequest()]);
      expect(MockNotification.requestPermission).toHaveBeenCalled();
      MockNotification.permission = 'granted';
    });

    it('does nothing when notification permission is denied', () => {
      MockNotification.permission = 'denied';
      notifyIdleApproval([makeRequest()]);
      expect(mockNotificationInstances).toHaveLength(0);
      MockNotification.permission = 'granted';
    });
  });

  describe('closeNotification', () => {
    it('closes specific notification by requestId', () => {
      notifyIdleApproval([makeRequest({ requestId: 'req-close' })]);
      expect(mockNotificationInstances).toHaveLength(1);
      closeNotification('req-close');
      expect(mockNotificationInstances[0].close).toHaveBeenCalled();
    });

    it('no-op for unknown requestId', () => {
      closeNotification('non-existent');
      // Should not throw
    });
  });

  describe('clearAllNotifications', () => {
    it('closes all notifications and stops title flash', () => {
      notifyIdleApproval([makeRequest({ requestId: 'r1' })]);
      notifyIdleApproval([makeRequest({ requestId: 'r2' })]);
      clearAllNotifications();
      for (const n of mockNotificationInstances) {
        expect(n.close).toHaveBeenCalled();
      }
    });

    it('restores original title', () => {
      const title = 'My App';
      document.title = title;
      notifyIdleApproval([makeRequest()]);
      vi.advanceTimersByTime(1000);
      clearAllNotifications();
      expect(document.title).toBe(title);
    });
  });

  describe('buildNotificationBody (via notifyIdleApproval)', () => {
    it('single request shows tool name and remaining seconds', () => {
      notifyIdleApproval([makeRequest({ toolName: 'shell_tool', reason: 'Execute rm -rf' })]);
      expect(mockNotificationInstances[0].body).toContain('Execute rm -rf');
      expect(mockNotificationInstances[0].body).toMatch(/\u5269\u4f59 \d+ \u79d2/);
    });

    it('multiple requests shows count and tool names', () => {
      const requests = [
        makeRequest({ requestId: 'r1', toolName: 'file_write_tool', batchId: 'b1' }),
        makeRequest({ requestId: 'r2', toolName: 'shell_tool', batchId: 'b1' }),
      ];
      notifyIdleApproval(requests);
      expect(mockNotificationInstances[0].body).toContain('file_write_tool');
      expect(mockNotificationInstances[0].body).toContain('shell_tool');
    });
  });

  describe('notification click handler', () => {
    it('focuses window and dispatches custom event on click', () => {
      const focusSpy = vi.spyOn(window, 'focus').mockImplementation(() => {});
      const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

      notifyIdleApproval([makeRequest({ requestId: 'click-test' })]);
      const notification = mockNotificationInstances[0];
      notification.onclick?.();

      expect(focusSpy).toHaveBeenCalled();
      expect(dispatchSpy).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'approval-notification-clicked' }),
      );
    });
  });

  describe('Tauri environment', () => {
    it('attempts Tauri notification when in Tauri environment', async () => {
      vi.mocked(isTauriEnvironment).mockReturnValue(true);

      const mockSendNotification = vi.fn();
      const mockIsPermissionGranted = vi.fn(() => Promise.resolve(true));
      const mockRequestPermission = vi.fn();
      const mockGetCurrentWindow = vi.fn(() => ({ requestUserAttention: vi.fn() }));

      vi.doMock('@tauri-apps/plugin-notification', () => ({
        sendNotification: mockSendNotification,
        isPermissionGranted: mockIsPermissionGranted,
        requestPermission: mockRequestPermission,
      }));
      vi.doMock('@tauri-apps/api/window', () => ({
        getCurrentWindow: mockGetCurrentWindow,
      }));

      notifyIdleApproval([makeRequest()]);
      // Tauri path is async; notifications won't be in mockNotificationInstances
      expect(mockNotificationInstances).toHaveLength(0);
    });
  });
});
