'use client';

/**
 * Secret Redaction Preview Component for sensitive credential scrubbing.
 *
 * [INPUT] redactionSummary: RedactionSummary | null, enableRedaction: boolean, onToggleRedaction
 * [OUTPUT] SecretRedactionPreview: Visual security panel detailing detected secrets and toggle switch.
 * [POS] src/components/features/session-export/SecretRedactionPreview.tsx
 */

import { memo } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  Key,
  Lock,
  Network,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { RedactionSummary } from './sessionExportTypes';

export interface SecretRedactionPreviewProps {
  redactionSummary: RedactionSummary | null;
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

export const SecretRedactionPreview = memo(function SecretRedactionPreview({
  redactionSummary,
  enableRedaction,
  onToggleRedaction,
  className,
}: SecretRedactionPreviewProps) {
  const t = useTranslations('sessionExport');

  const totalCount = redactionSummary?.total_redacted ?? 0;
  const hasSecrets = Boolean(redactionSummary?.has_secrets && totalCount > 0);

  return (
    <div
      className={cn(
        'rounded-xl border p-3 flex flex-col gap-2 transition-all',
        hasSecrets && enableRedaction
          ? 'bg-emerald-500/5 border-emerald-500/30'
          : hasSecrets && !enableRedaction
            ? 'bg-rose-500/5 border-rose-500/30'
            : 'bg-muted/20 border-border/70',
        className,
      )}
      data-testid="secret-redaction-preview"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div
            className={cn(
              'p-1.5 rounded-lg flex-shrink-0',
              hasSecrets && enableRedaction
                ? 'bg-emerald-500/10 text-emerald-500'
                : hasSecrets && !enableRedaction
                  ? 'bg-rose-500/10 text-rose-500'
                  : 'bg-muted/50 text-muted-foreground',
            )}
          >
            {hasSecrets && enableRedaction ? (
              <ShieldCheck className="h-4 w-4" />
            ) : hasSecrets && !enableRedaction ? (
              <ShieldAlert className="h-4 w-4" />
            ) : (
              <ShieldCheck className="h-4 w-4" />
            )}
          </div>

          <div>
            <h4 className="text-xs font-semibold text-foreground">
              {hasSecrets
                ? t('secretsDetected', { count: totalCount }) || `${totalCount} sensitive credentials detected`
                : t('cleanNoSecrets') || 'Clean session: no credentials detected'}
            </h4>
            <p className="text-[10px] text-muted-foreground">
              {enableRedaction
                ? t('redactionActiveHint') || 'API keys, passwords, and private IPs will be automatically scrubbed upon export.'
                : t('redactionDisabledHint') || 'Warning: sensitive keys will be exported in plaintext.'}
            </p>
          </div>
        </div>

        {/* Toggle Switch */}
        <label className="flex items-center gap-1.5 cursor-pointer select-none">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('autoRedact') || 'Auto-Redact'}
          </span>
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
      {hasSecrets && redactionSummary && redactionSummary.details.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-border/40">
          {redactionSummary.details.map((item, idx) => {
            const Icon = PATTERN_ICONS[item.pattern_type] || Key;
            return (
              <span
                key={`${item.pattern_type}-${idx}`}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-muted/60 text-[10px] font-mono text-muted-foreground border border-border/50"
              >
                <Icon className="h-3 w-3 flex-shrink-0" />
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
