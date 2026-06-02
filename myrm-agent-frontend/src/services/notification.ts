import { toast } from 'sonner';

export interface NotificationOptions {
  body?: string;
  icon?: string;
  onClick?: () => void;
}

class SystemNotificationService {
  /**
   * Check if the browser supports notifications
   */
  get isSupported(): boolean {
    return typeof window !== 'undefined' && 'Notification' in window;
  }

  /**
   * Get current permission status
   */
  get permission(): NotificationPermission {
    if (!this.isSupported) return 'denied';
    return Notification.permission;
  }

  /**
   * Request permission from the user
   */
  async requestPermission(): Promise<NotificationPermission> {
    if (!this.isSupported) return 'denied';
    if (this.permission === 'granted') return 'granted';

    try {
      return await Notification.requestPermission();
    } catch (error) {
      console.error('Failed to request notification permission:', error);
      return 'denied';
    }
  }

  /**
   * Send a notification.
   * Smart fallback:
   * 1. If page is visible, don't send OS notification, just use toast (if requested).
   * 2. If page is hidden and permission granted, send OS notification.
   * 3. If permission denied or not supported, fallback to toast.
   */
  notify(title: string, options?: NotificationOptions & { fallbackToToast?: boolean }) {
    const isVisible = typeof document !== 'undefined' && document.visibilityState === 'visible';
    const fallbackToToast = options?.fallbackToToast ?? true;

    // If page is visible, we don't want to spam OS notifications.
    // Just use toast if fallback is enabled.
    if (isVisible) {
      if (fallbackToToast) {
        toast(title, { description: options?.body });
      }
      return;
    }

    // Page is hidden. Try OS notification.
    if (this.isSupported && this.permission === 'granted') {
      try {
        const notification = new Notification(title, {
          body: options?.body,
          icon: options?.icon || '/favicon.ico', // Default icon if available
        });

        notification.onclick = () => {
          // Focus the window when clicked
          window.focus();
          notification.close();
          if (options?.onClick) {
            options.onClick();
          }
        };
      } catch (error) {
        console.error('Failed to show OS notification:', error);
        if (fallbackToToast) {
          toast(title, { description: options?.body });
        }
      }
    } else if (fallbackToToast) {
      // Fallback to toast if OS notification is not available
      toast(title, { description: options?.body });
    }
  }
}

export const notificationService = new SystemNotificationService();
