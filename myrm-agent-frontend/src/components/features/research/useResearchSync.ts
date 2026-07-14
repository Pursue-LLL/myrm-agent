'use client';

import { useEffect, useMemo } from 'react';
import useChatStore from '@/store/useChatStore';
import useResearchStore from '@/store/useResearchStore';
import type { MentionReference, MentionReferenceType } from '@/store/chat/types/messages';

const RESEARCH_TYPES: MentionReferenceType[] = ['wiki_concept', 'wiki_raw_file'];

/**
 * Syncs selected Research resources into ChatStore's mentionReferences.
 * Only manages wiki_concept/wiki_raw_file types, preserving user's manual @ references.
 */
export function useResearchSync() {
  const resources = useResearchStore((s) => s.resources);
  const addMentionReference = useChatStore((s) => s.addMentionReference);
  const removeMentionReferencesByTypes = useChatStore((s) => s.removeMentionReferencesByTypes);

  const selectedKey = useMemo(
    () => resources.filter((r) => r.selected).map((r) => r.id).join(','),
    [resources],
  );

  useEffect(() => {
    removeMentionReferencesByTypes(RESEARCH_TYPES);

    const selected = resources.filter((r) => r.selected);
    for (const resource of selected) {
      const ref: MentionReference = resource.type === 'concept'
        ? {
            type: 'wiki_concept',
            label: resource.name,
            source: 'special',
            size: null,
            conceptName: resource.name,
          }
        : {
            type: 'wiki_raw_file',
            label: resource.name,
            path: resource.id.replace('file:', ''),
            source: 'special',
            size: null,
          };
      addMentionReference(ref);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey]);

  useEffect(() => {
    return () => {
      removeMentionReferencesByTypes(RESEARCH_TYPES);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
