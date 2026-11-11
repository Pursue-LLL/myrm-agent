/**
 * [INPUT]
 * - next-intl::useTranslations (POS: interface translations)
 * - chat-export::MessageLabels (POS: the labelled parts of a copied or exported message, type-only)
 *
 * [OUTPUT]
 * - useMessageLabels: the labels in the interface language, one stable object per language
 *
 * [POS]
 * The words a copied or exported message uses for its reasoning and sources, taken from the interface translations so
 * the text reads in the language the reader sees on screen.
 */
import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import type { MessageLabels } from '@/lib/utils/chat-export';

export function useMessageLabels(): MessageLabels {
  const t = useTranslations('chat');
  const tSources = useTranslations('sources');
  return useMemo(
    () => ({ reasoning: t('reasoningTitle'), sources: tSources('title'), untitledSource: tSources('untitled') }),
    [t, tSources],
  );
}
