'use client';

import { useState, useEffect, useCallback } from 'react';
import { Bell, RefreshCw } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { apiRequest } from '@/lib/api';
import useAuthStore from '@/store/useAuthStore';
import { cn } from '@/lib/utils/classnameUtils';
import { formatRelativeTime } from '@/lib/utils/relativeTime';
import { toast } from '@/lib/utils/toast';
import { activateOnKey } from '@/lib/utils/a11y';

interface SystemNotificationMeta {
  action_url?: string;
  chat_id?: string;
  delivery_id?: string;
  retried?: boolean;
  /** Catalog keys + params for the copy, so the bell renders it in the reader's locale. */
  i18n_title_key?: string;
  i18n_message_key?: string;
  i18n_params?: Record<string, string>;
}

interface SystemNotification {
  id: string;
  title: string;
  message: string;
  type: 'info' | 'success' | 'warning' | 'error';
  source: string;
  is_read: boolean;
  created_at: string;
  meta_data?: SystemNotificationMeta | null;
}

interface NotificationListResponse {
  items: SystemNotification[];
  total: number;
  unread_count: number;
}

/**
 * Render a stored notification's copy in the reader's locale.
 *
 * The server stores English title/message plus optional catalog keys in ``meta_data``;
 * when the keys are present they win (so the notification center is localized), and
 * anything stored before the keys existed keeps rendering its stored text.
 */
function resolveNotificationCopy(
  notif: SystemNotification,
  translate: (key: string, values?: Record<string, string>) => string,
): { title: string; message: string } {
  const meta = notif.meta_data;
  const params = meta?.i18n_params ?? {};
  const localized = (key: string | undefined, fallback: string): string => {
    if (!key) {
      return fallback;
    }
    try {
      return translate(key, params) || fallback;
    } catch {
      return fallback;
    }
  };
  return {
    title: localized(meta?.i18n_title_key, notif.title),
    message: localized(meta?.i18n_message_key, notif.message),
  };
}

export default function NotificationBell() {
  const t = useTranslations('notifications');
  const translateCatalog = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const [notifications, setNotifications] = useState<SystemNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isOpen, setIsOpen] = useState(false);
  const [retryingIds, setRetryingIds] = useState<Set<string>>(new Set());

  const fetchNotifications = useCallback(async () => {
    if (!isAuthenticated) {
      return;
    }
    try {
      const res = await apiRequest<NotificationListResponse>('/notifications?limit=20');
      setNotifications(res.items || []);
      setUnreadCount(res.unread_count || 0);
    } catch (e) {
      console.error('Failed to fetch notifications', e);
    }
  }, [isAuthenticated]);

  const markAllAsRead = async () => {
    if (unreadCount === 0) {
      return;
    }
    try {
      await apiRequest('/notifications/read-all', { method: 'POST' });
      setUnreadCount(0);
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch (e) {
      console.error('Failed to mark notifications as read', e);
    }
  };

  const handleNotificationClick = (notif: SystemNotification) => {
    if (!notif.is_read) {
      setNotifications((prev) => prev.map((n) => (n.id === notif.id ? { ...n, is_read: true } : n)));
      setUnreadCount((prev) => Math.max(0, prev - 1));
      apiRequest(`/notifications/${notif.id}/read`, { method: 'POST' }).catch(() => {});
    }
    const actionUrl = notif.meta_data?.action_url;
    if (actionUrl) {
      setIsOpen(false);
      router.push(actionUrl);
    }
  };

  const handleRetry = async (e: React.MouseEvent, notifId: string) => {
    e.stopPropagation();
    if (retryingIds.has(notifId)) {
      return;
    }

    try {
      setRetryingIds((prev) => new Set(prev).add(notifId));
      await apiRequest(`/notifications/${notifId}/retry`, { method: 'POST' });
      toast.success(t('retrySuccess'));
      fetchNotifications();
    } catch (err) {
      console.error('Retry failed', err);
      toast.error(t('retryFailed'));
    } finally {
      setRetryingIds((prev) => {
        const next = new Set(prev);
        next.delete(notifId);
        return next;
      });
    }
  };

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  // Also refresh when global SSE event fires
  useEffect(() => {
    const handleSseEvent = () => fetchNotifications();
    window.addEventListener('message_dead_lettered', handleSseEvent);
    window.addEventListener('system_notification', handleSseEvent);
    return () => {
      window.removeEventListener('message_dead_lettered', handleSseEvent);
      window.removeEventListener('system_notification', handleSseEvent);
    };
  }, [fetchNotifications]);

  const handleOpenChange = (open: boolean) => {
    setIsOpen(open);
    if (open) {
      fetchNotifications();
    }
  };

  if (!isAuthenticated) {
    return null;
  }

  return (
    <Popover open={isOpen} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <button
          className="relative w-10 h-10 rounded-xl flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          aria-label={t('title')}
        >
          <Bell size={18} />
          {unreadCount > 0 && (
            <span className="absolute top-2 right-2 flex h-2.5 w-2.5 items-center justify-center rounded-full bg-red-500 ring-2 ring-background" />
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent side="right" align="end" sideOffset={8} className="w-80 p-0 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/30">
          <h3 className="font-semibold text-sm">{t('title')}</h3>
          {unreadCount > 0 && (
            <button
              onClick={markAllAsRead}
              className="text-xs text-primary hover:text-primary/80 transition-colors font-medium"
            >
              {t('markAllRead')}
            </button>
          )}
        </div>
        <div className="max-h-[400px] overflow-y-auto">
          {notifications.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">{t('empty')}</div>
          ) : (
            <div className="flex flex-col">
              {notifications.map((notif) => {
                const copy = resolveNotificationCopy(notif, translateCatalog);
                return (
                // oxlint-disable-next-line jsx-a11y/no-static-element-interactions -- dynamic role is not resolvable by static analysis
                <div
                  key={notif.id}
                  role={notif.meta_data?.action_url ? 'button' : undefined}
                  tabIndex={notif.meta_data?.action_url ? 0 : undefined}
                  onClick={() => handleNotificationClick(notif)}
                  onKeyDown={activateOnKey}
                  className={cn(
                    'p-4 border-b border-border/50 last:border-0 transition-colors',
                    !notif.is_read ? 'bg-primary/5' : 'hover:bg-muted/50',
                    notif.meta_data?.action_url && 'cursor-pointer',
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={cn(
                        'mt-0.5 w-2 h-2 rounded-full flex-shrink-0',
                        notif.type === 'error'
                          ? 'bg-red-500'
                          : notif.type === 'warning'
                            ? 'bg-amber-500'
                            : notif.type === 'success'
                              ? 'bg-green-500'
                              : 'bg-blue-500',
                      )}
                    />
                    <div className="flex-1 space-y-1 min-w-0">
                      <p className="text-sm font-medium leading-none text-foreground">{copy.title}</p>
                      <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">{copy.message}</p>
                      <div className="flex items-center justify-between pt-1">
                        <p className="text-[10px] text-muted-foreground/70">
                          {formatRelativeTime(notif.created_at, locale)}
                        </p>
                        {notif.type === 'error' && notif.meta_data?.delivery_id && !notif.meta_data?.retried && (
                          <button
                            onClick={(e) => handleRetry(e, notif.id)}
                            disabled={retryingIds.has(notif.id)}
                            className="flex items-center gap-1 text-[10px] font-medium text-primary hover:text-primary/80 transition-colors disabled:opacity-50"
                          >
                            <RefreshCw size={10} className={cn(retryingIds.has(notif.id) && 'animate-spin')} />
                            {t('retry')}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
                );
              })}
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
