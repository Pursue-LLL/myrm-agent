'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { AlertTriangle, X } from 'lucide-react';

import { cn } from '@/lib/utils/classnameUtils';
import { useMemoryStore } from '@/store/memory';

interface MemoryConflictChatBannerProps {
  chatId?: string;
  className?: string;
}

const MemoryConflictChatBanner = memo<MemoryConflictChatBannerProps>(({ chatId, className }) => {
  const t = useTranslations('memory');
  const conflictCount = useMemoryStore((s) => s.conflictCount);
  const fetchConflicts = useMemoryStore((s) => s.fetchConflicts);
  const [dismissed, setDismissed] = useState(false);

  const dismissKey = chatId ? `memory-conflict-banner:${chatId}` : 'memory-conflict-banner:global';

  useEffect(() => {
    void fetchConflicts();
  }, [fetchConflicts]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    setDismissed(window.sessionStorage.getItem(dismissKey) === '1');
  }, [dismissKey]);

  const handleDismiss = useCallback(() => {
    setDismissed(true);
    if (typeof window !== 'undefined') {
      window.sessionStorage.setItem(dismissKey, '1');
    }
  }, [dismissKey]);

  if (dismissed || conflictCount <= 0) {
    return null;
  }

  return (
    <div
      className={cn(
        'mx-auto mb-2 flex max-w-3xl w-full items-start gap-3 rounded-xl border border-amber-500/35',
        'bg-amber-500/8 px-3 py-2.5 text-sm shadow-sm backdrop-blur-sm',
        'max-sm:mx-2 max-sm:max-w-none',
        className,
      )}
      role="status"
      data-testid="memory-conflict-chat-banner"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-medium text-foreground leading-snug">
          {t('conflict.chatBannerTitle', {
            count: conflictCount,
            defaultMessage:
              conflictCount === 1
                ? 'One memory conflict needs your review'
                : '{count} memory conflicts need your review',
          })}
        </p>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {t('conflict.lowRiskPolicyHint', {
            defaultMessage:
              'Lower-importance conflicts keep the previous memory if you do not choose within about 72 hours.',
          })}
        </p>
        <Link
          href="/settings/memory?tab=pending"
          className="inline-flex text-xs font-medium text-primary hover:underline"
        >
          {t('conflict.chatBannerAction', { defaultMessage: 'Review in Memory settings' })}
        </Link>
      </div>
      <button
        type="button"
        onClick={handleDismiss}
        className="rounded-md p-1 text-muted-foreground hover:bg-muted/60 hover:text-foreground"
        aria-label={t('conflict.chatBannerDismiss', { defaultMessage: 'Dismiss for this chat session' })}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
});

MemoryConflictChatBanner.displayName = 'MemoryConflictChatBanner';

export default MemoryConflictChatBanner;
