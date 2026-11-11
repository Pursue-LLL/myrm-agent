/**
 * [INPUT]
 * - next-intl::useTranslations (POS: interface translations)
 * - chat-export::MessageLabels (POS: the labelled parts of a copied or exported message, type-only)
 * - wiki/sectionLabels::wikiSectionLabeler (POS: how a wiki section is worded)
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
import { wikiSectionLabeler } from '@/services/wiki/sectionLabels';

export function useMessageLabels(): Required<MessageLabels> {
  const t = useTranslations('chat');
  const tSources = useTranslations('sources');
  const tSections = useTranslations('MessageSources');
  return useMemo(
    () => ({
      reasoning: t('reasoningTitle'),
      sources: tSources('title'),
      untitledSource: tSources('untitled'),
      sectionLabel: wikiSectionLabeler(tSections),
    }),
    [t, tSources, tSections],
  );
}
