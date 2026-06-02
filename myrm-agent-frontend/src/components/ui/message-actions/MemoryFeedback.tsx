'use client';

import { ThumbsUp, ThumbsDown, Loader2 } from 'lucide-react';
import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { rateMemory } from '@/services/memory';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

type FeedbackState = 'idle' | 'up' | 'down' | 'loading';

const MemoryFeedback = ({ memoryIds }: { memoryIds: string[] }) => {
  const [state, setState] = useState<FeedbackState>('idle');
  const t = useTranslations('chat');

  const handleFeedback = useCallback(
    async (positive: boolean) => {
      if (state === 'loading') return;
      const newState = positive ? 'up' : 'down';
      if (state === newState) {
        setState('idle');
        return;
      }
      setState('loading');
      const score = positive ? 5 : 1;
      try {
        await Promise.allSettled(memoryIds.map((id) => rateMemory(id, score)));
        setState(newState);
      } catch {
        setState('idle');
      }
    },
    [memoryIds, state],
  );

  if (!memoryIds.length) return null;

  const btnBase = 'p-2 rounded-xl transition duration-200';

  return (
    <TooltipProvider delayDuration={300}>
      <div className="flex items-center">
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              className={`${btnBase} ${
                state === 'up'
                  ? 'text-green-500 bg-green-50 dark:bg-green-900/20'
                  : 'text-black/70 dark:text-white/70 hover:bg-secondary dark:hover:bg-secondary hover:text-black dark:hover:text-white'
              }`}
              onClick={() => handleFeedback(true)}
              disabled={state === 'loading'}
              aria-label={t('memoryFeedbackGood')}
            >
              {state === 'loading' ? <Loader2 size={18} className="animate-spin" /> : <ThumbsUp size={18} />}
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p>{t('memoryFeedbackGood')}</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <button
              className={`${btnBase} ${
                state === 'down'
                  ? 'text-red-500 bg-red-50 dark:bg-red-900/20'
                  : 'text-black/70 dark:text-white/70 hover:bg-secondary dark:hover:bg-secondary hover:text-black dark:hover:text-white'
              }`}
              onClick={() => handleFeedback(false)}
              disabled={state === 'loading'}
              aria-label={t('memoryFeedbackBad')}
            >
              <ThumbsDown size={18} />
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p>{t('memoryFeedbackBad')}</p>
          </TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  );
};

export default MemoryFeedback;
