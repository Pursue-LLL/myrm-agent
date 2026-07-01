'use client';

import { memo } from 'react';
import { ShieldCheck, ShieldX } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';

type E2EESecurityPanelProps = {
  established: boolean;
  fingerprint: string | null;
  algorithm: string;
  sessionIdPrefix: string | null;
  error: string | null;
};

/**
 * Reusable E2EE status badge with popover detail panel.
 * Shows green ShieldCheck when established, red ShieldX on error, hidden otherwise.
 */
const E2EESecurityPanel = memo<E2EESecurityPanelProps>(
  ({ established, fingerprint, algorithm, sessionIdPrefix, error }) => {
    const t = useTranslations('e2ee');

    if (error) {
      return (
        <div
          className="flex items-center gap-1.5 text-destructive"
          role="status"
          aria-label={t('handshakeFailed')}
        >
          <ShieldX className="h-4 w-4" />
          <span className="text-[10px] font-medium">{t('handshakeFailed')}</span>
        </div>
      );
    }

    if (!established) return null;

    return (
      <Popover>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-emerald-400 transition-colors hover:bg-emerald-500/20"
            role="status"
            aria-label={t('secured')}
          >
            <ShieldCheck className="h-3.5 w-3.5" />
            <span className="text-[10px] font-semibold uppercase tracking-wide">{t('secured')}</span>
          </button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-64 space-y-3 p-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
            <span className="text-sm font-semibold">{t('securityInfo')}</span>
          </div>
          <dl className="space-y-2 text-xs">
            <div>
              <dt className="text-muted-foreground">{t('algorithm')}</dt>
              <dd className="font-mono">{algorithm}</dd>
            </div>
            {fingerprint && (
              <div>
                <dt className="text-muted-foreground">{t('fingerprint')}</dt>
                <dd className="font-mono tracking-wider">{fingerprint}</dd>
              </div>
            )}
            {sessionIdPrefix && (
              <div>
                <dt className="text-muted-foreground">{t('sessionId')}</dt>
                <dd className="font-mono">{sessionIdPrefix}…</dd>
              </div>
            )}
          </dl>
        </PopoverContent>
      </Popover>
    );
  },
);

E2EESecurityPanel.displayName = 'E2EESecurityPanel';

export default E2EESecurityPanel;
