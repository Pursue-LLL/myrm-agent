'use client';

/**
 * ExternalBrowserButton Component.
 * Explicit "Open in External Browser" button to render single-file deliverables
 * in real native browser, bypassing iframe CSP & anti-hotlinking broken images.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Check, ExternalLink, Loader2 } from 'lucide-react';
import { ExternalPreviewButtonStatus } from './externalPreviewTypes';
import { ExternalPreviewService } from './externalPreviewService';

interface ExternalBrowserButtonProps {
  content: string;
  title?: string;
  className?: string;
  compact?: boolean;
}

export const ExternalBrowserButton: React.FC<ExternalBrowserButtonProps> = ({
  content,
  title = 'Deliverable Preview',
  className = '',
  compact = false,
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('skillAlignment');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback in test suites
  }

  const [status, setStatus] = useState<ExternalPreviewButtonStatus>('idle');

  const handleOpenBrowser = async (): Promise<void> => {
    if (status === 'opening') {
      return;
    }
    setStatus('opening');
    try {
      await ExternalPreviewService.openInExternalBrowser({
        content,
        title,
      });
      setStatus('success');
      setTimeout(() => {
        setStatus('idle');
      }, 2000);
    } catch {
      setStatus('error');
      setTimeout(() => {
        setStatus('idle');
      }, 3000);
    }
  };

  return (
    <button
      type="button"
      onClick={handleOpenBrowser}
      disabled={status === 'opening'}
      title={t('openInBrowserDesc')}
      aria-label={t('openInBrowser')}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
        status === 'success'
          ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-400'
          : status === 'error'
          ? 'bg-rose-500/15 border border-rose-500/30 text-rose-400'
          : 'bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700 text-slate-200 hover:text-white'
      } ${className}`}
    >
      {status === 'opening' ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
      ) : status === 'success' ? (
        <Check className="w-3.5 h-3.5 text-emerald-400" />
      ) : (
        <ExternalLink className="w-3.5 h-3.5 text-slate-300" />
      )}
      {!compact && (
        <span>
          {status === 'opening'
            ? t('opening')
            : status === 'success'
            ? t('opened')
            : t('openInBrowser')}
        </span>
      )}
    </button>
  );
};
