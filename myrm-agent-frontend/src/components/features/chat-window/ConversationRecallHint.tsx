'use client';

/**
 * [INPUT]
 * @/store/useConfigStore (POS: Global memory policy configuration store)
 *
 * [OUTPUT]
 * ConversationRecallHint: EmptyChat discovery banner for opt-in conversation recall.
 *
 * [POS]
 * Guides GUI users to enable conversation history search without forcing the toggle on.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';

import { Button } from '@/components/primitives/button';
import useConfigStore from '@/store/useConfigStore';
import { IconArrowRight } from '@/components/features/icons/PremiumIcons';

const DISMISS_KEY = 'conversation_recall_hint_dismissed';

export default function ConversationRecallHint() {
  const t = useTranslations('chat.conversationRecall');
  const enabled = useConfigStore((s) => s.memoryEnableConversationSearch);
  const [dismissed, setDismissed] = useState(true);

  useEffect(() => {
    try {
      setDismissed(sessionStorage.getItem(DISMISS_KEY) === 'true');
    } catch {
      setDismissed(false);
    }
  }, []);

  const handleDismiss = useCallback(() => {
    setDismissed(true);
    try {
      sessionStorage.setItem(DISMISS_KEY, 'true');
    } catch {
      /* ignore */
    }
  }, []);

  if (enabled || dismissed) {
    return null;
  }

  return (
    <div className="w-full max-w-screen-md lg:max-w-[820px] mx-auto px-4">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-xl border border-border/50 bg-accent/20 px-4 py-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground">{t('hintTitle')}</p>
          <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{t('hintBody')}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="ghost" size="sm" onClick={handleDismiss} className="text-xs">
            {t('dismiss')}
          </Button>
          <Button asChild size="sm" variant="outline" className="text-xs gap-1">
            <Link href="/settings/memory">
              {t('openSettings')}
              <IconArrowRight className="w-3.5 h-3.5" />
            </Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
