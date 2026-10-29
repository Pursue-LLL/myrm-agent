'use client';

/**
 * Secret Redaction Preview Component for sensitive credential scrubbing.
 *
 * [INPUT] scan: RedactionScan, enableRedaction: boolean, onToggleRedaction
 * [OUTPUT] SecretRedactionPreview: Security panel stating whether the scan is running, unavailable, clean or found credentials, plus the auto-redact switch.
 * [POS] src/components/features/session-export/SecretRedactionPreview.tsx
 */

import { memo } from 'react';
import { ShieldCheck, ShieldAlert, ShieldQuestionMark, Key, Loader2, Lock, Network } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { RedactionScan } from './sessionExportTypes';

export interface SecretRedactionPreviewProps {
  scan: RedactionScan;
  enableRedaction: boolean;
  onToggleRedaction: (enabled: boolean) => void;
  className?: string;
}

const PATTERN_ICONS: Record<string, typeof Key> = {
  api_key: Key,
  jwt_token: Lock,
  bearer_token: Lock,
  secret_assignment: Lock,
  internal_ip: Network,
};

type Tone = 'neutral' | 'safe' | 'danger';

const TONE_STYLES: Record<Tone, { panel: string; icon: string }> = {
  neutral: { panel: 'bg-muted/20 border-border/70', icon: 'bg-muted/50 text-muted-foreground' },
  safe: { panel: 'bg-emerald-500/5 border-emerald-500/30', icon: 'bg-emerald-500/10 text-emerald-500' },
  danger: { panel: 'bg-rose-500/5 border-rose-500/30', icon: 'bg-rose-500/10 text-rose-500' },
};

export const SecretRedactionPreview = memo(function SecretRedactionPreview({
  scan,
  enableRedaction,
  onToggleRedaction,
  className,
}: SecretRedactionPreviewProps) {
  const t = useTranslations('sessionExport');

  const summary = scan.status === 'ready' ? scan.summary : null;
  const totalCount = summary?.total_redacted ?? 0;
  const hasSecrets = Boolean(summary?.has_secrets && totalCount > 0);
  const tone: Tone = hasSecrets ? (enableRedaction ? 'safe' : 'danger') : 'neutral';

  let Icon = ShieldCheck;
  let title = t('cleanNoSecrets');
  if (scan.status === 'scanning') {
    Icon = Loader2;
    title = t('scanningSecrets');
  } else if (scan.status === 'failed') {
    Icon = ShieldQuestionMark;
    title = t('scanUnavailable');
  } else if (hasSecrets) {
    Icon = enableRedaction ? ShieldCheck : ShieldAlert;
    title = t('secretsDetected', { count: totalCount });
  }

  return (
    <div
      className={cn('rounded-xl border p-3 flex flex-col gap-2 transition-all', TONE_STYLES[tone].panel, className)}
      data-testid="secret-redaction-preview"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className={cn('p-1.5 rounded-lg flex-shrink-0', TONE_STYLES[tone].icon)}>
            <Icon className={cn('h-4 w-4', scan.status === 'scanning' && 'animate-spin motion-reduce:animate-none')} />
          </div>

          <div aria-live="polite">
            <h4 className="text-xs font-semibold text-foreground">{title}</h4>
            <p className="text-[10px] text-muted-foreground">
              {enableRedaction ? t('redactionActiveHint') : t('redactionDisabledHint')}
            </p>
          </div>
        </div>

        {/* Toggle Switch */}
        <label className="flex items-center gap-1.5 cursor-pointer select-none">
          <span className="text-[11px] font-medium text-muted-foreground">{t('autoRedact')}</span>
          <input
            type="checkbox"
            checked={enableRedaction}
            onChange={(e) => {
              onToggleRedaction(e.target.checked);
            }}
            className="w-3.5 h-3.5 rounded border-border text-primary focus:ring-primary/40 cursor-pointer"
            data-testid="redaction-checkbox"
          />
        </label>
      </div>

      {/* Pattern Breakdown Pills */}
      {hasSecrets && summary && summary.details.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-border/40">
          {summary.details.map((item) => {
            const PatternIcon = PATTERN_ICONS[item.pattern_type] || Key;
            return (
              <span
                key={item.pattern_type}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-muted/60 text-[10px] font-mono text-muted-foreground border border-border/50"
              >
                <PatternIcon className="h-3 w-3 flex-shrink-0" />
                <span>
                  {item.pattern_type}: {item.count}
                </span>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
});
