'use client';

import React, { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Monitor, ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { apiRequest } from '@/lib/api';
import useDesktopControlApprovalStore, {
  type DesktopControlApprovalScope,
} from '@/store/useDesktopControlApprovalStore';

async function resolveApproval(
  requestId: string,
  granted: boolean,
  scope: DesktopControlApprovalScope = 'once',
): Promise<void> {
  await apiRequest('/webui/desktop/approval/resolve', {
    method: 'POST',
    body: JSON.stringify({ request_id: requestId, granted, scope }),
  });
}

const DesktopControlApprovalBanner: React.FC = () => {
  const t = useTranslations('chat.desktopInspector.controlApproval');
  const {
    pending,
    requestId,
    reason,
    operation,
    appName,
    windowTitle,
    requireAppApproval,
    clear,
  } = useDesktopControlApprovalStore();
  const [submitting, setSubmitting] = useState(false);

  const handleDecision = useCallback(
    async (granted: boolean, scope: DesktopControlApprovalScope = 'once') => {
      if (!requestId || submitting) return;
      setSubmitting(true);
      try {
        await resolveApproval(requestId, granted, scope);
      } catch {
        // Keep banner visible so the user can retry
        setSubmitting(false);
        return;
      }
      clear();
      setSubmitting(false);
    },
    [requestId, submitting, clear],
  );

  if (!pending) return null;

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
              <span className="truncate">{appName}{windowTitle ? ` — ${windowTitle}` : ''}</span>
            </p>
          ) : null}
          <p className="text-sm text-foreground/90">{reason}</p>
          <p className="text-xs text-muted-foreground font-mono truncate">{operation}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 justify-end">
        <button
          type="button"
          disabled={submitting}
          className="px-3 py-1.5 text-xs rounded-lg border border-border hover:bg-muted transition-colors disabled:opacity-50"
          onClick={() => void handleDecision(false)}
        >
          {t('deny')}
        </button>
        <button
          type="button"
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
              disabled={submitting}
              className="hidden sm:inline-flex px-3 py-1.5 text-xs rounded-lg border border-primary/40 text-primary hover:bg-primary/10 transition-colors disabled:opacity-50"
              onClick={() => void handleDecision(true, 'session')}
            >
              {t('allowSession')}
            </button>
            <button
              type="button"
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
