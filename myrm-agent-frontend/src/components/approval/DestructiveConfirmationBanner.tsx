'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertOctagon, Camera, FileWarning, ShieldAlert } from 'lucide-react';

export interface DestructiveBlastRadius {
  command?: string;
  reason?: string;
  destructiveCount?: number;
  impact_scope?: string;
  affected_targets?: string[];
  summary_reason?: string;
}

interface DestructiveConfirmationBannerProps {
  blastRadius?: DestructiveBlastRadius;
  snapshotId?: string;
  onConfirmationChange: (confirmed: boolean) => void;
  disabled?: boolean;
}

const REQUIRED_CONFIRM_KEYWORD = 'CONFIRM';

export function DestructiveConfirmationBanner({
  blastRadius,
  snapshotId,
  onConfirmationChange,
  disabled = false,
}: DestructiveConfirmationBannerProps) {
  const t = useTranslations('toolApproval.irreversibleDestructive');
  const [inputText, setInputText] = useState('');

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setInputText(val);
    const isMatched = val.trim() === REQUIRED_CONFIRM_KEYWORD;
    onConfirmationChange(isMatched);
  };

  const isConfirmed = inputText.trim() === REQUIRED_CONFIRM_KEYWORD;

  return (
    <div
      className="space-y-3 rounded-lg border border-red-500/50 bg-red-500/10 p-4 dark:border-red-500/40 dark:bg-red-950/25"
      data-testid="destructive-confirmation-banner"
      role="alert"
    >
      <div className="flex items-start gap-3">
        <AlertOctagon className="h-5 w-5 shrink-0 text-red-600 dark:text-red-400 mt-0.5" aria-hidden="true" />
        <div className="space-y-1">
          <h4 className="font-semibold text-sm text-red-700 dark:text-red-300">{t('title')}</h4>
          <p className="text-xs text-red-600/90 dark:text-red-400/90 leading-relaxed">{t('description')}</p>
        </div>
      </div>

      {blastRadius && (
        <div className="rounded-md border border-red-500/30 bg-background/80 p-3 space-y-2 text-xs">
          <div className="flex items-center gap-1.5 font-medium text-red-700 dark:text-red-300">
            <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{t('blastRadiusLabel')}</span>
            {blastRadius.impact_scope && (
              <span className="ml-auto rounded bg-red-100 dark:bg-red-900/40 px-2 py-0.5 font-mono text-[11px] text-red-800 dark:text-red-300 border border-red-300 dark:border-red-700">
                {blastRadius.impact_scope}
              </span>
            )}
          </div>

          {blastRadius.summary_reason && (
            <p className="text-muted-foreground">{blastRadius.summary_reason}</p>
          )}

          {Array.isArray(blastRadius.affected_targets) && blastRadius.affected_targets.length > 0 && (
            <div className="space-y-1">
              <span className="text-[11px] text-muted-foreground">目标路径 / 影响对象:</span>
              <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
                {blastRadius.affected_targets.map((target, idx) => (
                  <code
                    key={idx}
                    className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-red-700 dark:text-red-400 border border-border"
                  >
                    {target}
                  </code>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-2 text-xs rounded-md bg-background/60 p-2.5 border border-border/60">
        {snapshotId ? (
          <>
            <Camera className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
            <div className="flex items-center gap-2 overflow-hidden">
              <span className="text-emerald-700 dark:text-emerald-300 font-medium">{t('snapshotReady')}:</span>
              <code className="font-mono text-[11px] text-muted-foreground truncate">{snapshotId.slice(0, 16)}</code>
            </div>
          </>
        ) : (
          <>
            <FileWarning className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
            <span className="text-amber-700 dark:text-amber-300 font-medium">{t('snapshotNone')}</span>
          </>
        )}
      </div>

      <div className="space-y-1.5 pt-1">
        <label
          htmlFor="destructive-confirm-input"
          className="text-xs font-medium text-red-700 dark:text-red-300 flex items-center justify-between"
        >
          <span>{t('confirmPrompt')}</span>
          {isConfirmed && (
            <span className="text-emerald-600 dark:text-emerald-400 font-semibold text-[11px]">
              已就绪 / Ready
            </span>
          )}
        </label>
        <div className="relative">
          <input
            id="destructive-confirm-input"
            type="text"
            value={inputText}
            onChange={handleInputChange}
            disabled={disabled}
            placeholder={REQUIRED_CONFIRM_KEYWORD}
            className={`w-full rounded-md border px-3 py-1.5 text-xs font-mono tracking-wider transition-colors outline-none focus:ring-1 ${
              isConfirmed
                ? 'border-emerald-500 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 focus:border-emerald-500 focus:ring-emerald-500'
                : 'border-red-400 bg-background text-foreground focus:border-red-500 focus:ring-red-500'
            }`}
            autoComplete="off"
            spellCheck="false"
          />
        </div>
      </div>
    </div>
  );
}
