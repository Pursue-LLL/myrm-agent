/**
 * [INPUT]
 * StructuredApprovalRequest from visualDiffTypes.ts
 * [OUTPUT]
 * ApprovalNotificationBridge: Cross-platform native interactive notification dispatch for Desktop and Web.
 * [POS]
 * src/components/approval/visual-diff/ApprovalNotificationBridge.ts
 */

import { StructuredApprovalRequest } from './visualDiffTypes';

export class ApprovalNotificationBridge {
  static async requestPermission(): Promise<boolean> {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      return false;
    }
    if (Notification.permission === 'granted') {
      return true;
    }
    if (Notification.permission !== 'denied') {
      const permission = await Notification.requestPermission();
      return permission === 'granted';
    }
    return false;
  }

  static async notifyApprovalRequired(
    request: StructuredApprovalRequest,
    options?: { onActionClick?: () => void }
  ): Promise<boolean> {
    if (typeof window === 'undefined') {
      return false;
    }

    const title = 'Myrmidon Action Approval Required';
    const body = `${request.summary} [Press 1 to Allow, 2 to Reject]`;

    // 1. Try Desktop Tauri Notification if window.__TAURI__ is available
    interface TauriNotificationHost {
      __TAURI__?: {
        notification?: {
          sendNotification: (options: { title: string; body: string }) => void;
        };
      };
    }

    const tauriHost = window as unknown as TauriNotificationHost;
    if (tauriHost.__TAURI__?.notification?.sendNotification) {
      try {
        tauriHost.__TAURI__.notification.sendNotification({ title, body });
        return true;
      } catch {
        // Fallback to standard web notification
      }
    }

    // 2. Fallback to Web Notification API
    if ('Notification' in window && Notification.permission === 'granted') {
      try {
        const notification = new Notification(title, {
          body,
          icon: '/favicon.ico',
          tag: request.approval_id,
        });

        if (options?.onActionClick) {
          notification.onclick = () => {
            window.focus();
            options.onActionClick?.();
            notification.close();
          };
        }
        return true;
      } catch {
        return false;
      }
    }

    return false;
  }
}
