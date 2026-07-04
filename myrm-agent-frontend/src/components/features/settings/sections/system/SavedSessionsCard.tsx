/**
 * [INPUT]
 * GET /api/v1/browser/sessions — list saved browser sessions
 * DELETE /api/v1/browser/sessions/:domain — delete a session
 * POST /api/v1/browser/sessions/cleanup — cleanup expired sessions
 *
 * [OUTPUT]
 * SavedSessionsCard: browser saved-session management card for system settings
 *
 * [POS]
 * Displays a list of AES-256-encrypted saved browser login sessions
 * (cookies/localStorage) with domain, expiry status, and management actions.
 */

'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { IconKey, IconTrash, IconRefresh } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';

interface SessionSummary {
  domain: string;
  created_at: string;
  expires_at: string | null;
  is_expired: boolean;
  cookie_count: number;
  local_storage_count: number;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const SavedSessionsCard = memo(() => {
  const t = useTranslations('settings.savedSessions');
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingDomain, setDeletingDomain] = useState<string | null>(null);
  const [cleaningUp, setCleaningUp] = useState(false);

  const fetchSessions = useCallback(async () => {
    try {
      const resp = await fetch(`${getBackendUrl()}/api/v1/browser/sessions`, {
        headers: getAuthHeaders(),
      });
      if (resp.ok) {
        setSessions(await resp.json());
      }
    } catch {
      /* server may be offline */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchSessions();
  }, [fetchSessions]);

  const handleDelete = useCallback(
    async (domain: string) => {
      setDeletingDomain(domain);
      try {
        const resp = await fetch(
          `${getBackendUrl()}/api/v1/browser/sessions/${encodeURIComponent(domain)}`,
          { method: 'DELETE', headers: getAuthHeaders() },
        );
        if (resp.ok) {
          setSessions((prev) => prev.filter((s) => s.domain !== domain));
          toast.success(t('deleteSuccess', { domain }));
        } else {
          toast.error(t('deleteFailed'));
        }
      } catch {
        toast.error(t('deleteFailed'));
      } finally {
        setDeletingDomain(null);
      }
    },
    [t],
  );

  const handleCleanup = useCallback(async () => {
    setCleaningUp(true);
    try {
      const resp = await fetch(`${getBackendUrl()}/api/v1/browser/sessions/cleanup`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (resp.ok) {
        const data = await resp.json();
        toast.success(t('cleanupSuccess', { count: data.removed }));
        void fetchSessions();
      }
    } catch {
      toast.error(t('cleanupFailed'));
    } finally {
      setCleaningUp(false);
    }
  }, [fetchSessions, t]);

  const expiredCount = sessions.filter((s) => s.is_expired).length;

  return (
    <div className="rounded-xl border border-border/50 bg-card/60 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <IconKey className="w-4 h-4 text-amber-500" />
          <div>
            <h4 className="text-sm font-medium text-foreground">{t('title')}</h4>
            <p className="text-xs text-muted-foreground">{t('description')}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {expiredCount > 0 && (
            <button
              onClick={handleCleanup}
              disabled={cleaningUp}
              className={cn(
                'px-2 py-1 rounded-md text-xs font-medium transition-colors',
                'bg-amber-500/10 text-amber-600 hover:bg-amber-500/20',
                'dark:text-amber-400 dark:hover:bg-amber-500/30',
                cleaningUp && 'opacity-50 cursor-not-allowed',
              )}
            >
              {cleaningUp ? t('cleaning') : t('cleanupExpired', { count: expiredCount })}
            </button>
          )}
          <button
            onClick={() => {
              setLoading(true);
              void fetchSessions();
            }}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
          >
            <IconRefresh className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-xs text-muted-foreground py-4 text-center">{t('loading')}</div>
      ) : sessions.length === 0 ? (
        <div className="text-xs text-muted-foreground py-4 text-center">{t('empty')}</div>
      ) : (
        <div className="space-y-1.5 max-h-64 overflow-y-auto">
          {sessions.map((session) => (
            <div
              key={session.domain}
              className={cn(
                'flex items-center justify-between px-3 py-2 rounded-lg',
                'bg-muted/30 hover:bg-muted/50 transition-colors',
                session.is_expired && 'opacity-60',
              )}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-foreground truncate">
                    {session.domain}
                  </span>
                  {session.is_expired && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-500/10 text-red-500 dark:text-red-400 font-medium">
                      {t('expired')}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5">
                  <span className="text-[10px] text-muted-foreground">
                    {t('cookies')}: {session.cookie_count}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {t('localStorage')}: {session.local_storage_count}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {formatDate(session.created_at)}
                  </span>
                  {session.expires_at && (
                    <span className="text-[10px] text-muted-foreground">
                      → {formatDate(session.expires_at)}
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={() => handleDelete(session.domain)}
                disabled={deletingDomain === session.domain}
                className={cn(
                  'p-1.5 rounded-md text-muted-foreground hover:text-red-500 hover:bg-red-500/10 transition-colors ml-2',
                  deletingDomain === session.domain && 'opacity-50 cursor-not-allowed',
                )}
                title={t('delete')}
              >
                <IconTrash className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      <p className="text-[10px] text-muted-foreground/70">{t('encryptionNote')}</p>
    </div>
  );
});

SavedSessionsCard.displayName = 'SavedSessionsCard';

export default SavedSessionsCard;
