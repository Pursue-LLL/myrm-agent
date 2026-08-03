/**
 * [INPUT]
 * - useConfigStore::enableIdleApprovalNotification, approvalNotificationSound
 * - useToolApprovalStore::queue (ToolApprovalRequest)
 * - isTauriEnvironment (lib/tauri)
 * - getClientLocale (lib/utils/localeUtils) (POS: Locale 工具集)
 * - Locale (i18n/config) (POS: 支持 locale 列表)
 *
 * [OUTPUT]
 * - OS-level system notifications when window is inactive and approval arrives
 * - Tab title flashing for WebUI fallback
 * - Automatic notification cleanup on approval resolution
 *
 * [POS]
 * Idle Approval Alert — bridges the gap between "approval waiting in UI" and
 * "user doesn't know because window is background". Prevents approval timeout
 * deny from silently killing tasks.
 */

import type { Locale } from '@/i18n/config';
import { isTauriEnvironment } from '@/lib/tauri';
import { getClientLocale } from '@/lib/utils/localeUtils';
import { getConfigSyncManager } from '@/services/config';
import type { ToolApprovalRequest } from '@/store/chat/types';

const MAX_ACTIVE_NOTIFICATIONS = 5;
const TITLE_FLASH_INTERVAL_MS = 1000;

interface NotificationStrings {
  pending: string;
  pendingMulti: string;
  remaining: string;
  includes: string;
}

const NOTIFICATION_I18N: Record<Locale, NotificationStrings> = {
  en: { pending: 'Approval Pending', pendingMulti: '{count} actions pending approval', remaining: 'remaining {seconds}s', includes: 'includes' },
  zh: { pending: '审批等待', pendingMulti: '{count} 个操作等待审批', remaining: '剩余 {seconds} 秒', includes: '包含' },
  'zh-TW': { pending: '審批等待', pendingMulti: '{count} 個操作等待審批', remaining: '剩餘 {seconds} 秒', includes: '包含' },
  ja: { pending: '承認待ち', pendingMulti: '{count} 件の操作が承認待ち', remaining: '残り {seconds} 秒', includes: '含む' },
  ko: { pending: '승인 대기', pendingMulti: '{count}개 작업 승인 대기', remaining: '남은 시간 {seconds}초', includes: '포함' },
  de: { pending: 'Genehmigung ausstehend', pendingMulti: '{count} Aktionen warten auf Genehmigung', remaining: 'verbleibend {seconds}s', includes: 'enthält' },
};

function getNotificationStrings(): NotificationStrings {
  const locale = (getClientLocale() ?? 'en') as Locale;
  return NOTIFICATION_I18N[locale] ?? NOTIFICATION_I18N['en'];
}

let originalTitle: string | null = null;
let titleFlashTimer: ReturnType<typeof setInterval> | null = null;
let activeNotifications = new Map<string, Notification>();

function isPageHidden(): boolean {
  return typeof document !== 'undefined' && document.hidden;
}

function getConfig(): { enabled: boolean; sound: boolean } {
  try {
    const settings = getConfigSyncManager().get('personalSettings');
    return {
      enabled: settings?.enableIdleApprovalNotification ?? true,
      sound: settings?.approvalNotificationSound ?? true,
    };
  } catch {
    return { enabled: true, sound: true };
  }
}

function buildNotificationBody(requests: ToolApprovalRequest[]): { title: string; body: string } {
  const strings = getNotificationStrings();
  if (requests.length === 1) {
    const req = requests[0];
    const remaining = Math.max(0, Math.round(req.expiresAt - Date.now() / 1000));
    return {
      title: `⚠️ ${strings.pending} - ${req.toolName}`,
      body: `${req.reason}, ${strings.remaining.replace('{seconds}', String(remaining))}`,
    };
  }
  return {
    title: `⚠️ ${strings.pendingMulti.replace('{count}', String(requests.length))}`,
    body: `${strings.includes} ${requests.map((r) => r.toolName).join(', ')}`,
  };
}

async function sendTauriNotification(title: string, body: string, requestId: string, sound: boolean): Promise<void> {
  try {
    const { sendNotification, requestPermission, isPermissionGranted } = await import(
      '@tauri-apps/plugin-notification'
    );
    let granted = await isPermissionGranted();
    if (!granted) {
      const permission = await requestPermission();
      granted = permission === 'granted';
    }
    if (!granted) return;

    sendNotification({ title, body, sound: sound ? 'default' : undefined });

    const { getCurrentWindow } = await import('@tauri-apps/api/window');
    const win = getCurrentWindow();
    await win.requestUserAttention(2); // Critical
  } catch {
    // Tauri API not available (e.g. running in browser mode during dev)
  }
}

function sendBrowserNotification(
  title: string,
  body: string,
  requestId: string,
  _sound: boolean,
): void {
  if (typeof window === 'undefined' || !('Notification' in window)) return;
  if (Notification.permission === 'default') {
    Notification.requestPermission();
    return;
  }
  if (Notification.permission !== 'granted') return;

  const notification = new Notification(title, {
    body,
    tag: `myrm-approval-${requestId}`,
    requireInteraction: true,
  });

  notification.onclick = () => {
    window.focus();
    notification.close();
  };

  activeNotifications.set(requestId, notification);
  pruneNotifications();
}

function pruneNotifications(): void {
  while (activeNotifications.size > MAX_ACTIVE_NOTIFICATIONS) {
    const oldest = activeNotifications.keys().next().value;
    if (!oldest) break;
    closeNotification(oldest);
  }
}

let visibilityListenerAttached = false;

function ensureVisibilityListener(): void {
  if (visibilityListenerAttached || typeof document === 'undefined') return;
  visibilityListenerAttached = true;
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) stopTitleFlash();
  });
}

function startTitleFlash(): void {
  if (titleFlashTimer) return;
  if (typeof document === 'undefined') return;
  ensureVisibilityListener();
  originalTitle = document.title;
  const flashTitle = `⚠️ ${getNotificationStrings().pending}`;
  let isAlternate = false;
  titleFlashTimer = setInterval(() => {
    isAlternate = !isAlternate;
    document.title = isAlternate ? flashTitle : (originalTitle || 'MyrmAgent');
  }, TITLE_FLASH_INTERVAL_MS);
}

function stopTitleFlash(): void {
  if (!titleFlashTimer) return;
  clearInterval(titleFlashTimer);
  titleFlashTimer = null;
  if (typeof document !== 'undefined' && originalTitle !== null) {
    document.title = originalTitle;
    originalTitle = null;
  }
}

/**
 * Notify user about pending approval(s) when window is inactive.
 * Handles batch grouping: same batchId approvals are merged into one notification.
 */
export function notifyIdleApproval(requests: ToolApprovalRequest[]): void {
  if (!isPageHidden()) return;
  const { enabled, sound } = getConfig();
  if (!enabled) return;
  if (requests.length === 0) return;

  // Batch grouping: group by batchId, non-batch get individual notifications
  const groups = new Map<string, ToolApprovalRequest[]>();
  for (const req of requests) {
    const key = req.batchId || req.requestId;
    const existing = groups.get(key) || [];
    existing.push(req);
    groups.set(key, existing);
  }

  for (const [groupKey, groupRequests] of groups) {
    const { title, body } = buildNotificationBody(groupRequests);

    if (isTauriEnvironment()) {
      sendTauriNotification(title, body, groupKey, sound);
    } else {
      sendBrowserNotification(title, body, groupKey, sound);
    }
  }

  startTitleFlash();
}

/**
 * Close notification for a resolved approval.
 */
export function closeNotification(requestId: string): void {
  const notification = activeNotifications.get(requestId);
  if (notification) {
    try { notification.close(); } catch { /* ignore */ }
    activeNotifications.delete(requestId);
  }
}

/** Whether the approval title flash is currently active. Used by tab badge to yield priority. */
export function isTitleFlashing(): boolean {
  return titleFlashTimer !== null;
}

/**
 * Clear all approval notifications (e.g. when all approvals are resolved or user focuses window).
 */
export function clearAllNotifications(): void {
  for (const [id] of activeNotifications) {
    closeNotification(id);
  }
  activeNotifications.clear();
  stopTitleFlash();
}
