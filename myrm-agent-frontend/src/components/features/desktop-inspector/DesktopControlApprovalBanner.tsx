'use client';

import React, { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { History, Monitor, ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { ApiError, apiRequest } from '@/lib/api';
import useDesktopControlApprovalStore, {
  type DesktopControlApprovalScope,
} from '@/store/useDesktopControlApprovalStore';

async function resolveApproval(
  requestId: string,
  granted: boolean,
  scope: DesktopControlApprovalScope = 'once',
  reason = '',
): Promise<void> {
  await apiRequest('/webui/desktop/approval/resolve', {
    method: 'POST',
    // Omit an empty rationale so the wire shape stays identical to the
    // pre-reason contract; the backend defaults it to "".
    body: JSON.stringify({
      request_id: requestId,
      granted,
      scope,
      ...(reason ? { reason } : {}),
    }),
  });
}

const DesktopControlApprovalBanner: React.FC = () => {
  const t = useTranslations('chat.desktopInspector.controlApproval');
  const { pending, expired, changed, requestId, reason, operation, appName, windowTitle, requireAppApproval, clear, markExpired } =
    useDesktopControlApprovalStore();
  const [submitting, setSubmitting] = useState(false);
  const [denyReason, setDenyReason] = useState('');

  const handleDecision = useCallback(
    async (granted: boolean, scope: DesktopControlApprovalScope = 'once') => {
      if (!requestId || submitting) {
        return;
      }
      setSubmitting(true);
      try {
        await resolveApproval(requestId, granted, scope, granted ? '' : denyReason.trim());
      } catch (err) {
        // Settled requests (timeout/duplicate resolve) move to the expired
        // view; transport errors keep the banner so the user can retry.
        if (err instanceof ApiError && err.code === 410) {
          markExpired();
          setSubmitting(false);
          return;
        }
        setSubmitting(false);
        return;
      }
      clear();
      setDenyReason('');
      setSubmitting(false);
    },
    [requestId, submitting, denyReason, clear, markExpired],
  );

  if (!pending) {
    return null;
  }

  if (expired) {
    return (
      <div
        className={cn(
          'mx-3 mb-3 rounded-xl border border-border bg-background',
          'shadow-lg backdrop-blur-sm p-4 space-y-3',
        )}
      >
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-lg bg-muted p-2 text-muted-foreground shrink-0">
            <History className="h-4 w-4" aria-hidden />
          </div>
          <div className="min-w-0 flex-1 space-y-1">
            <p className="text-sm font-semibold text-foreground">{t('title')}</p>
            <p className="text-xs text-muted-foreground">{t('expiredNotice')}</p>
            {operation ? (
              <p className="text-xs text-muted-foreground font-mono truncate">{operation}</p>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 justify-end">
          <button
            type="button"
            data-testid="desktop-control-expired-dismiss"
            className="px-3 py-1.5 text-xs rounded-lg border border-border hover:bg-muted transition-colors"
            onClick={() => clear()}
          >
            {t('dismiss')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'mx-3 mb-3 rounded-xl border border-primary/30 bg-gradient-to-br from-primary/10 via-background to-background',
        'shadow-lg backdrop-blur-sm p-4 space-y-3',
      )}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 rounded-lg bg-primary/15 p-2 text-primary shrink-0">
          <ShieldAlert className="h-4 w-4" aria-hidden />
        </div>
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-sm font-semibold text-foreground">{t('title')}</p>
          {requireAppApproval && appName ? (
            <p className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Monitor className="h-3.5 w-3.5 shrink-0" aria-hidden />
              <span className="truncate">
                {appName}
                {windowTitle ? ` — ${windowTitle}` : ''}
              </span>
            </p>
          ) : null}
          <p className="text-sm text-foreground/90">{reason}</p>
          <p className="text-xs text-muted-foreground font-mono truncate">{operation}</p>
          {changed ? (
            <p className="text-xs text-amber-600 dark:text-amber-400">{t('targetChangedNotice')}</p>
          ) : null}
        </div>
      </div>

      <input
        type="text"
        value={denyReason}
        maxLength={200}
        onChange={(event) => setDenyReason(event.target.value)}
        placeholder={t('denyReasonPlaceholder')}
        aria-label={t('denyReasonPlaceholder')}
        className="w-full px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50"
      />

      <div className="flex flex-wrap gap-2 justify-end">
        <button
          type="button"
          data-testid="desktop-control-deny"
          disabled={submitting}
          className="px-3 py-1.5 text-xs rounded-lg border border-border hover:bg-muted transition-colors disabled:opacity-50"
          onClick={() => void handleDecision(false)}
        >
          {t('deny')}
        </button>
        <button
          type="button"
          data-testid="desktop-control-allow-once"
          disabled={submitting}
          className="px-3 py-1.5 text-xs rounded-lg bg-primary/90 text-primary-foreground hover:bg-primary transition-colors disabled:opacity-50"
          onClick={() => void handleDecision(true, 'once')}
        >
          {t('allowOnce')}
        </button>
        {requireAppApproval ? (
          <>
            <button
              type="button"
              data-testid="desktop-control-allow-session"
              disabled={submitting}
              className="hidden sm:inline-flex px-3 py-1.5 text-xs rounded-lg border border-primary/40 text-primary hover:bg-primary/10 transition-colors disabled:opacity-50"
              onClick={() => void handleDecision(true, 'session')}
            >
              {t('allowSession')}
            </button>
            <button
              type="button"
              data-testid="desktop-control-allow-always"
              disabled={submitting}
              className="hidden md:inline-flex px-3 py-1.5 text-xs rounded-lg border border-primary/40 text-primary hover:bg-primary/10 transition-colors disabled:opacity-50"
              onClick={() => void handleDecision(true, 'always')}
            >
              {t('allowAlways')}
            </button>
          </>
        ) : null}
      </div>
    </div>
  );
};

export default DesktopControlApprovalBanner;
