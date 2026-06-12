'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import Link from 'next/link';
import { cn } from '@/lib/utils/classnameUtils';
import { useNavBadges } from '@/hooks/useNavBadges';
import useChatStore from '@/store/useChatStore';
import { useShallow } from 'zustand/react/shallow';

export default function ExtensionDisconnectedBanner() {
  const t = useTranslations('extensionBanner');
  const [dismissed, setDismissed] = useState(false);
  const badges = useNavBadges();
  const browserSource = useChatStore(
    useShallow((s) => s.agentConfig?.browserSource),
  );

  useEffect(() => {
    if (badges.extensionConnected) setDismissed(false);
  }, [badges.extensionConnected]);

  const needsExtension = browserSource === 'extension';
  if (!needsExtension || badges.extensionConnected || dismissed) return null;

  return (
    <div
      role="alert"
      aria-live="polite"
      className={cn(
        'relative overflow-hidden border-b border-amber-500/20',
        'bg-gradient-to-r from-amber-500/10 via-amber-500/5 to-transparent',
        'backdrop-blur-md supports-[backdrop-filter]:bg-amber-500/5',
      )}
    >
      <div className="absolute inset-y-0 left-0 w-[3px] bg-gradient-to-b from-amber-500/80 via-amber-500 to-amber-500/40" />
      <div
        className={cn(
          'flex items-center justify-between gap-2',
          'px-3 py-2 pl-4 sm:px-4 sm:pl-5',
        )}
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <span
            className={cn(
              'flex h-6 w-6 shrink-0 items-center justify-center rounded-full',
              'bg-amber-500/15 text-amber-600 ring-1 ring-amber-500/25',
              'dark:bg-amber-500/20 dark:text-amber-400 dark:ring-amber-500/30',
            )}
          >
            <AlertTriangle className="h-3 w-3" aria-hidden />
          </span>
          <p className="text-xs leading-snug text-amber-700 dark:text-amber-300">
            {t('message')}{' '}
            <Link
              href="/settings/browser"
              className="font-medium underline underline-offset-2 hover:text-amber-900 dark:hover:text-amber-100"
            >
              {t('connect')}
            </Link>
          </p>
        </div>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="shrink-0 rounded p-0.5 text-amber-600/60 hover:text-amber-700 dark:text-amber-400/60 dark:hover:text-amber-300 transition-colors"
          aria-label={t('dismiss')}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
