'use client';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { getWorkingState, type WorkingStateResponse } from '@/services/memory';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';

/**
 * Compact, read-only surface for the persisted cross-session working state.
 *
 * The state itself is injected into the memory context by the server; this badge only
 * makes the saved note visible while the user is in the chat. It carries no runtime
 * subtasks or traps.
 */
export interface WorkingStateBadgeProps {
  chatId?: string;
}

const WorkingStateBadge = memo(({ chatId }: WorkingStateBadgeProps = {}) => {
  const t = useTranslations('chat.workingState');
  const [state, setState] = useState<WorkingStateResponse | null>(null);
  const loading = useChatStore((s) => s.loading);
  const incognito = useChatStore((s) => s.incognitoMode);
  const isMessagesLoaded = useChatStore((s) => s.isMessagesLoaded);
  const memoryEnabled = useConfigStore((s) => s.enableMemory);
  const chatReady = !chatId || isMessagesLoaded;
  const previousLoading = useRef(loading);

  const fetchState = useCallback(async () => {
    try {
      setState(await getWorkingState());
    } catch {
      setState(null);
    }
  }, []);

  useEffect(() => {
    if (!chatReady || !memoryEnabled || incognito) {
      setState(null);
      return;
    }
    void fetchState();
  }, [chatReady, fetchState, incognito, memoryEnabled]);

  useEffect(() => {
    if (chatReady && memoryEnabled && !incognito && previousLoading.current && !loading) {
      void fetchState();
    }
    previousLoading.current = loading;
  }, [chatReady, fetchState, incognito, loading, memoryEnabled]);

  if (!chatReady || !memoryEnabled || incognito || !state?.content || state.expired) {
    return null;
  }

  return (
    <div className="w-full max-w-3xl mx-auto px-4 py-1">
      <details className="group rounded-lg border border-primary/20 bg-primary/5 px-3 py-2">
        <summary className="flex cursor-pointer list-none items-center gap-2 text-sm">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden="true" />
          <span className="font-medium">{t('title')}</span>
          <span className="truncate text-xs text-muted-foreground">{state.content}</span>
          <ChevronDown
            className="ml-auto h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
            aria-hidden="true"
          />
        </summary>
        <p className="mt-2 whitespace-pre-wrap break-words text-sm text-foreground/80">{state.content}</p>
      </details>
    </div>
  );
});

WorkingStateBadge.displayName = 'WorkingStateBadge';
export default WorkingStateBadge;
