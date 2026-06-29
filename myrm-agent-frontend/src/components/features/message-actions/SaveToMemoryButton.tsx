'use client';

/**
 * [INPUT]
 * @/services/memory::createMemory (POS: Frontend Memory API client)
 * @/store/chat/types::Message (POS: Chat state and SSE event type definitions)
 *
 * [OUTPUT]
 * SaveToMemoryButton: One-click save assistant message to long-term memory.
 *
 * [POS]
 * Chat message action button. Saves message content as semantic memory via existing createMemory API.
 */

import { useCallback, useState } from 'react';
import { BrainCircuit, Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { createMemory } from '@/services/memory';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import type { Message } from '@/store/chat/types';

type SaveState = 'idle' | 'saving' | 'saved';

export default function SaveToMemoryButton({ message }: { message: Message }) {
  const t = useTranslations('chat');
  const [state, setState] = useState<SaveState>('idle');

  const handleSave = useCallback(async () => {
    if (state !== 'idle') return;
    setState('saving');
    try {
      await createMemory({
        memory_type: 'semantic',
        content: message.content,
        importance: 0.8,
      });
      setState('saved');
      toast.success(t('saveToMemory.success'));
    } catch {
      setState('idle');
      toast.error(t('saveToMemory.error'));
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
              state === 'saved'
                ? 'text-green-500 bg-green-50 dark:bg-green-900/20'
                : 'text-black/70 dark:text-white/70 hover:bg-light-secondary dark:hover:bg-dark-secondary hover:text-black dark:hover:text-white active:scale-95'
            }`}
            onClick={() => void handleSave()}
            disabled={state !== 'idle'}
            aria-label={t('saveToMemory.title')}
          >
            {state === 'saving' ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <BrainCircuit className="w-4 h-4" />
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          <p>{state === 'saved' ? t('saveToMemory.saved') : t('saveToMemory.title')}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
