import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';
import { notificationService } from '../notification';

vi.mock('sonner', () => ({
  toast: vi.fn(),
}));

const mockToast = toast as unknown as ReturnType<typeof vi.fn>;

describe('SystemNotificationService', () => {
  beforeEach(() => {
    mockToast.mockClear();
  });

  describe('isSupported', () => {
    it('returns true when Notification API exists', () => {
      Object.defineProperty(window, 'Notification', {
        value: { permission: 'default', requestPermission: vi.fn() },
        writable: true,
        configurable: true,
      });
      expect(notificationService.isSupported).toBe(true);
    });
  });

  describe('permission', () => {
    it('returns current Notification permission', () => {
      Object.defineProperty(window, 'Notification', {
        value: { permission: 'granted', requestPermission: vi.fn() },
        writable: true,
        configurable: true,
      });
      expect(notificationService.permission).toBe('granted');
    });
  });

  describe('requestPermission', () => {
    it('returns granted when already granted', async () => {
      Object.defineProperty(window, 'Notification', {
        value: { permission: 'granted', requestPermission: vi.fn() },
        writable: true,
        configurable: true,
      });
      const result = await notificationService.requestPermission();
      expect(result).toBe('granted');
    });

    it('requests permission when not yet granted', async () => {
      const mockRequest = vi.fn().mockResolvedValue('granted');
      Object.defineProperty(window, 'Notification', {
        value: { permission: 'default', requestPermission: mockRequest },
        writable: true,
        configurable: true,
      });
      const result = await notificationService.requestPermission();
      expect(mockRequest).toHaveBeenCalled();
      expect(result).toBe('granted');
    });
  });

  describe('notify', () => {
    it('shows toast when page is visible', () => {
      Object.defineProperty(document, 'visibilityState', {
        value: 'visible',
        writable: true,
        configurable: true,
      });
      Object.defineProperty(window, 'Notification', {
        value: { permission: 'granted', requestPermission: vi.fn() },
        writable: true,
        configurable: true,
      });

      notificationService.notify('Test Title', { body: 'Test body' });

      expect(mockToast).toHaveBeenCalledWith('Test Title', { description: 'Test body' });
    });

    it('shows OS notification when page is hidden and permission granted', () => {
      Object.defineProperty(document, 'visibilityState', {
        value: 'hidden',
        writable: true,
        configurable: true,
      });

      const mockNotification = vi.fn();
      Object.defineProperty(window, 'Notification', {
        value: Object.assign(mockNotification, { permission: 'granted', requestPermission: vi.fn() }),
        writable: true,
        configurable: true,
      });

      notificationService.notify('Hidden Title', { body: 'Hidden body' });

      expect(mockNotification).toHaveBeenCalledWith('Hidden Title', {
        body: 'Hidden body',
        icon: '/favicon-32.png',
      });
      expect(mockToast).not.toHaveBeenCalled();
    });

    it('falls back to toast when page is hidden but permission denied', () => {
      Object.defineProperty(document, 'visibilityState', {
        value: 'hidden',
        writable: true,
        configurable: true,
      });
      Object.defineProperty(window, 'Notification', {
        value: { permission: 'denied', requestPermission: vi.fn() },
        writable: true,
        configurable: true,
      });

      notificationService.notify('Denied Title', { body: 'body' });

      expect(mockToast).toHaveBeenCalledWith('Denied Title', { description: 'body' });
    });

    it('does not show toast when fallbackToToast is false and page is visible', () => {
      Object.defineProperty(document, 'visibilityState', {
        value: 'visible',
        writable: true,
        configurable: true,
      });

      notificationService.notify('No Toast', { fallbackToToast: false });

      expect(mockToast).not.toHaveBeenCalled();
    });
  });
});
