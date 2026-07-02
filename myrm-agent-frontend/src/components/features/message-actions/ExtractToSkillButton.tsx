'use client';

/**
 * [INPUT]
 * @/store/useChatStore::sendMessage (POS: Active chat state manager)
 * @/store/chat/types::Message (POS: Chat state and SSE event type definitions)
 *
 * [OUTPUT]
 * ExtractToSkillButton: One-click extract assistant message into a reusable skill via /learn.
 *
 * [POS]
 * Chat message action button. Triggers /learn command with message content as context,
 * reusing the existing skill evolution pipeline (learn → draft → review → materialize).
 */

import { useCallback, useState } from 'react';
import { Sparkles, Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import useChatStore from '@/store/useChatStore';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import type { Message } from '@/store/chat/types';

type ExtractState = 'idle' | 'sending' | 'sent';

export default function ExtractToSkillButton({ message }: { message: Message }) {
  const t = useTranslations('chat');
  const [state, setState] = useState<ExtractState>('idle');

  const handleExtract = useCallback(async () => {
    if (state !== 'idle') return;
    setState('sending');
    try {
      const learnInput = `/learn ${t('extractToSkill.learnContext')}\n\n${message.content}`;
      await useChatStore.getState().sendMessage(learnInput);
      setState('sent');
      toast.success(t('extractToSkill.success'));
    } catch {
      setState('idle');
      toast.error(t('extractToSkill.error'));
    }
  }, [message.content, state, t]);

  if (!message.content.trim()) return null;

  const btnBase = 'p-2 rounded-xl transition duration-200';

  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className={`${btnBase} ${
              state === 'sent'
                ? 'text-purple-500 bg-purple-50 dark:bg-purple-900/20'
                : 'text-black/70 dark:text-white/70 hover:bg-light-secondary dark:hover:bg-dark-secondary hover:text-black dark:hover:text-white active:scale-95'
            }`}
            onClick={() => void handleExtract()}
            disabled={state !== 'idle'}
            aria-label={t('extractToSkill.title')}
          >
            {state === 'sending' ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          <p>{state === 'sent' ? t('extractToSkill.sent') : t('extractToSkill.title')}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
