'use client';

/**
 * Share-link tab of the session export modal: expiry window, optional passcode and the generated link with its copy button.
 *
 * [INPUT] ttlDays, password, result: ShareLinkResponse | null, copied, change/copy callbacks
 * [OUTPUT] ShareLinkPanel: Controlled form and result card for a read-only share link.
 * [POS] src/components/features/session-export/ShareLinkPanel.tsx
 */

import { memo } from 'react';
import { Calendar, Check, Copy, Lock } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { ShareLinkResponse } from './sessionExportTypes';

export interface ShareLinkPanelProps {
  ttlDays: number;
  onTtlDaysChange: (days: number) => void;
  password: string;
  onPasswordChange: (password: string) => void;
  result: ShareLinkResponse | null;
  copied: boolean;
  onCopy: () => void;
}

export const ShareLinkPanel = memo(function ShareLinkPanel({
  ttlDays,
  onTtlDaysChange,
  password,
  onPasswordChange,
  result,
  copied,
  onCopy,
}: ShareLinkPanelProps) {
  const t = useTranslations('sessionExport');

  return (
    <div className="p-4 flex flex-col gap-3 max-h-[75vh] overflow-y-auto text-xs">
      <div className="flex flex-col gap-2 p-3 rounded-xl border border-border/80 bg-muted/20">
        <div className="flex items-center justify-between">
          <span className="font-medium text-foreground flex items-center gap-1">
            <Calendar className="h-3.5 w-3.5 text-primary" />
            <span>{t('linkExpiry')}</span>
          </span>
          <select
            value={ttlDays}
            onChange={(e) => {
              onTtlDaysChange(Number(e.target.value));
            }}
            className="px-2 py-0.5 rounded border border-border bg-background text-xs text-foreground focus:outline-none"
          >
            <option value={7}>{t('expiry7Days')}</option>
            <option value={30}>{t('expiry30Days')}</option>
          </select>
        </div>

        <div className="flex flex-col gap-1 pt-1 border-t border-border/40">
          <span className="font-medium text-foreground flex items-center gap-1">
            <Lock className="h-3.5 w-3.5 text-muted-foreground" />
            <span>{t('optionalPassword')}</span>
          </span>
          <input
            type="password"
            value={password}
            onChange={(e) => {
              onPasswordChange(e.target.value);
            }}
            placeholder={t('passwordPlaceholder')}
            className="w-full px-2.5 py-1 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary/50 text-foreground"
          />
        </div>
      </div>

      {/* Generated Share Link Result Card */}
      {result && (
        <div className="flex flex-col gap-1.5 p-3 rounded-xl border border-primary/30 bg-primary/5">
          <span className="font-semibold text-[11px] text-primary">{t('shareLinkReady')}</span>
          <div className="flex items-center gap-2">
            <input
              type="text"
              readOnly
              value={result.share_url}
              className="flex-1 px-2.5 py-1 text-xs rounded-lg border border-border bg-background font-mono text-foreground"
              data-testid="share-url-input"
            />
            <button
              type="button"
              onClick={onCopy}
              className="flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-semibold bg-primary text-primary-foreground hover:opacity-90 active:scale-95 shadow-xs transition-all"
              data-testid="copy-link-btn"
            >
              {copied ? (
                <>
                  <Check className="h-3.5 w-3.5" />
                  <span>{t('copied')}</span>
                </>
              ) : (
                <>
                  <Copy className="h-3.5 w-3.5" />
                  <span>{t('copy')}</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
});
