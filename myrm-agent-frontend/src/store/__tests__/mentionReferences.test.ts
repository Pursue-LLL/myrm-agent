import { act } from '@testing-library/react';

import type { MentionReference } from '../chat/types/messages';
import useChatStore from '../useChatStore';

const makeRef = (type: MentionReference['type'], label: string): MentionReference => ({
  type,
  label,
  source: 'special',
  size: null,
  ...(type === 'wiki_concept' ? { conceptName: label } : {}),
  ...(type === 'workspace_file' ? { path: `/test/${label}` } : {}),
  ...(type === 'wiki_raw_file' ? { path: label } : {}),
  ...(type === 'url' ? { url: `https://${label}` } : {}),
});

describe('useChatStore mentionReferences', () => {
  beforeEach(() => {
    act(() => {
      useChatStore.getState().clearMentionReferences();
    });
  });

  describe('addMentionReference', () => {
    it('adds a reference', () => {
      const ref = makeRef('wiki_concept', 'ML');
      act(() => {
        useChatStore.getState().addMentionReference(ref);
      });
      expect(useChatStore.getState().mentionReferences).toHaveLength(1);
      expect(useChatStore.getState().mentionReferences[0].label).toBe('ML');
    });

    it('deduplicates by key', () => {
      const ref = makeRef('wiki_concept', 'ML');
      act(() => {
        useChatStore.getState().addMentionReference(ref);
        useChatStore.getState().addMentionReference(ref);
      });
      expect(useChatStore.getState().mentionReferences).toHaveLength(1);
    });
  });

  describe('removeMentionReferencesByTypes', () => {
    it('removes only specified types', () => {
      act(() => {
        const { addMentionReference } = useChatStore.getState();
        addMentionReference(makeRef('wiki_concept', 'ML'));
        addMentionReference(makeRef('wiki_raw_file', 'report.pdf'));
        addMentionReference(makeRef('workspace_file', 'main.py'));
        addMentionReference(makeRef('url', 'example.com'));
      });

      expect(useChatStore.getState().mentionReferences).toHaveLength(4);

      act(() => {
        useChatStore.getState().removeMentionReferencesByTypes(['wiki_concept', 'wiki_raw_file']);
      });

      const remaining = useChatStore.getState().mentionReferences;
      expect(remaining).toHaveLength(2);
      expect(remaining.map((r) => r.type)).toEqual(['workspace_file', 'url']);
    });

    it('preserves all references when types is empty', () => {
      act(() => {
        const { addMentionReference } = useChatStore.getState();
        addMentionReference(makeRef('wiki_concept', 'ML'));
        addMentionReference(makeRef('workspace_file', 'main.py'));
      });

      act(() => {
        useChatStore.getState().removeMentionReferencesByTypes([]);
      });

      expect(useChatStore.getState().mentionReferences).toHaveLength(2);
    });

    it('removes all references of a single type', () => {
      act(() => {
        const { addMentionReference } = useChatStore.getState();
        addMentionReference(makeRef('wiki_concept', 'ML'));
        addMentionReference(makeRef('wiki_concept', 'DL'));
        addMentionReference(makeRef('workspace_file', 'main.py'));
      });

      act(() => {
        useChatStore.getState().removeMentionReferencesByTypes(['wiki_concept']);
      });

      const remaining = useChatStore.getState().mentionReferences;
      expect(remaining).toHaveLength(1);
      expect(remaining[0].type).toBe('workspace_file');
    });

    it('handles no matching types gracefully', () => {
      act(() => {
        useChatStore.getState().addMentionReference(makeRef('workspace_file', 'main.py'));
      });

      act(() => {
        useChatStore.getState().removeMentionReferencesByTypes(['wiki_concept', 'wiki_raw_file']);
      });

      expect(useChatStore.getState().mentionReferences).toHaveLength(1);
    });
  });

  describe('clearMentionReferences', () => {
    it('removes all references', () => {
      act(() => {
        const { addMentionReference } = useChatStore.getState();
        addMentionReference(makeRef('wiki_concept', 'ML'));
        addMentionReference(makeRef('workspace_file', 'main.py'));
      });

      act(() => {
        useChatStore.getState().clearMentionReferences();
      });

      expect(useChatStore.getState().mentionReferences).toHaveLength(0);
    });
  });
});
