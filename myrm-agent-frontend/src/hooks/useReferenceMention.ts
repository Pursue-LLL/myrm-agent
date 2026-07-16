/**
 * @ reference autocomplete hook.
 *
 * [INPUT]
 * - @/services/chat::suggestReferences (POS: Server-side safe reference suggestions)
 *
 * [OUTPUT]
 * - useReferenceMention: hook providing reference mention state, keyboard nav and selection.
 *
 * [POS]
 * Chat input @ reference autocomplete. It keeps GUI product semantics in the
 * frontend while all workspace boundaries are resolved by the server.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { suggestReferences, type ReferenceSuggestion } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import useAgentStore from '@/store/useAgentStore';
import type { MentionReference } from '@/store/chat/types';

interface ReferenceMentionState {
  isOpen: boolean;
  results: ReferenceSuggestion[];
  selectedIndex: number;
  query: string;
  mentionStart: number;
}

const DEBOUNCE_MS = 180;

const STATIC_SPECIAL_RESULTS: ReferenceSuggestion[] = [
  {
    source: 'special',
    reference_type: 'git_staged',
    kind: 'reference',
    label: '@staged',
    basename: '@staged',
    directory: '',
    relative_path: null,
    file_id: null,
    description: 'Git staged changes',
    size: null,
    score_tier: 'prefix',
    score: 1000,
    match_ranges: [],
  },
  {
    source: 'special',
    reference_type: 'git_diff',
    kind: 'reference',
    label: '@diff',
    basename: '@diff',
    directory: '',
    relative_path: null,
    file_id: null,
    description: 'Git working tree changes',
    size: null,
    score_tier: 'prefix',
    score: 990,
    match_ranges: [],
  },
  {
    source: 'special',
    reference_type: 'workspace_folder',
    kind: 'directory',
    label: '@folder:',
    basename: '@folder:',
    directory: '',
    relative_path: null,
    file_id: null,
    description: 'Directory tree under workspace',
    size: null,
    score_tier: 'prefix',
    score: 980,
    match_ranges: [],
  },
  {
    source: 'special',
    reference_type: 'url',
    kind: 'reference',
    label: '@url:',
    basename: '@url:',
    directory: '',
    relative_path: null,
    file_id: null,
    description: 'Fetch webpage content',
    size: null,
    score_tier: 'prefix',
    score: 970,
    match_ranges: [],
  },
  {
    source: 'special',
    reference_type: 'wiki_concept',
    kind: 'reference',
    label: '@wiki:',
    basename: '@wiki:',
    directory: '',
    relative_path: null,
    file_id: null,
    description: 'Knowledge base concept',
    size: null,
    score_tier: 'prefix',
    score: 960,
    match_ranges: [],
  },
];

function extractMentionQuery(text: string, cursorPos: number): { query: string; start: number } | null {
  const before = text.slice(0, cursorPos);
  const atIndex = before.lastIndexOf('@');
  if (atIndex === -1) return null;
  if (atIndex > 0 && /\S/.test(before[atIndex - 1])) return null;

  const query = before.slice(atIndex + 1);
  if (query.includes('\n') || query.includes(' ')) return null;
  return { query, start: atIndex };
}

function staticSpecialMatches(query: string): ReferenceSuggestion[] {
  const lowerQuery = query.toLowerCase();
  return STATIC_SPECIAL_RESULTS.filter((item) => {
    const token = item.basename.replace(/^@/, '').replace(/:$/, '').toLowerCase();
    return !lowerQuery || token.startsWith(lowerQuery);
  });
}

function toMentionReference(item: ReferenceSuggestion): MentionReference | null {
  if (item.reference_type === 'url' && !item.label.startsWith('@url:http')) {
    return null;
  }
  if (item.reference_type === 'workspace_folder' && !item.relative_path) {
    return null;
  }
  if (item.reference_type === 'wiki_concept' && !item.concept_name) {
    return null;
  }
  const label = item.label.startsWith('@') ? item.label : `@${item.basename || item.label}`;
  return {
    type: item.reference_type,
    label,
    path: item.relative_path ?? undefined,
    fileId: item.file_id ?? undefined,
    url: item.reference_type === 'url' ? item.label.replace(/^@url:/, '') : undefined,
    source: item.source as MentionReference['source'],
    size: item.size,
    directory: item.directory || undefined,
    conceptName: item.concept_name ?? undefined,
  };
}

function replacementFor(item: ReferenceSuggestion, folderMode: boolean): string {
  if (item.reference_type === 'git_staged') return '@staged ';
  if (item.reference_type === 'git_diff') return '@diff ';
  if (item.reference_type === 'url') return '@url:';
  if (item.reference_type === 'workspace_folder') {
    if (item.relative_path) return `@folder:${item.relative_path} `;
    return '@folder:';
  }
  if (item.reference_type === 'wiki_concept') {
    if (item.concept_name) return `@wiki:${item.concept_name} `;
    return '@wiki:';
  }
  if (folderMode && item.relative_path) return `@folder:${item.relative_path} `;
  return `@${item.relative_path ?? item.label} `;
}

export const useReferenceMention = (inputMessage: string, cursorPosition: number) => {
  const [state, setState] = useState<ReferenceMentionState>({
    isOpen: false,
    results: [],
    selectedIndex: 0,
    query: '',
    mentionStart: -1,
  });
  const chatId = useChatStore((s) => s.chatId);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestSeqRef = useRef(0);

  useEffect(() => {
    void useAgentStore.getState().fetchAgents(1, 100, false);
  }, []);

  useEffect(() => {
    const mention = extractMentionQuery(inputMessage, cursorPosition);
    if (!mention) {
      setState((prev) => (prev.isOpen ? { ...prev, isOpen: false, results: [], selectedIndex: 0 } : prev));
      return;
    }

    const folderMode = mention.query.startsWith('folder:');
    const wikiMode = !folderMode && mention.query.startsWith('wiki:');
    const query = folderMode
      ? mention.query.slice('folder:'.length)
      : wikiMode
        ? mention.query.slice('wiki:'.length)
        : mention.query;
    const specialResults = folderMode || wikiMode ? [] : staticSpecialMatches(mention.query);

    setState((prev) => ({
      ...prev,
      isOpen: true,
      query: mention.query,
      mentionStart: mention.start,
      selectedIndex: 0,
      results: specialResults,
    }));

    if (!chatId) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;

    debounceRef.current = setTimeout(async () => {
      try {
        const data = await suggestReferences(chatId, query, 30, folderMode ? 'directory' : 'any');
        if (requestSeqRef.current !== requestSeq) return;
        const serverResults = folderMode
          ? data.results
          : wikiMode
            ? data.results.filter((item) => item.source === 'wiki')
            : data.results.filter((item) => item.source !== 'special');
        
        let agentResults: ReferenceSuggestion[] = [];
        if (!folderMode && !wikiMode) {
          const agents = useAgentStore.getState().agents;
          agentResults = agents
            .filter(a => !query || a.name.toLowerCase().includes(query.toLowerCase()))
            .map(a => ({
              source: 'agent',
              reference_type: 'agent',
              kind: 'agent',
              label: a.name,
              basename: a.name,
              directory: a.description || 'Agent',
              relative_path: null,
              file_id: a.id,
              description: a.description || null,
              size: null,
              score_tier: 'prefix',
              score: 2000,
              match_ranges: [],
              avatar_url: a.avatar_url
            }));
        }

        setState((prev) => ({
          ...prev,
          results: folderMode || wikiMode ? serverResults : [...agentResults, ...specialResults, ...serverResults],
          selectedIndex: 0,
        }));
      } catch {
        if (requestSeqRef.current !== requestSeq) return;

        let agentResults: ReferenceSuggestion[] = [];
        if (!folderMode && !wikiMode) {
          const agents = useAgentStore.getState().agents;
          agentResults = agents
            .filter(a => !query || a.name.toLowerCase().includes(query.toLowerCase()))
            .map(a => ({
              source: 'agent',
              reference_type: 'agent',
              kind: 'agent',
              label: a.name,
              basename: a.name,
              directory: a.description || 'Agent',
              relative_path: null,
              file_id: a.id,
              description: a.description || null,
              size: null,
              score_tier: 'prefix',
              score: 2000,
              match_ranges: [],
              avatar_url: a.avatar_url
            }));
        }

        setState((prev) => ({ ...prev, results: [...agentResults, ...specialResults], selectedIndex: 0 }));
      }
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [chatId, cursorPosition, inputMessage]);

  const dismiss = useCallback(() => {
    setState((prev) => ({ ...prev, isOpen: false, results: [], selectedIndex: 0 }));
  }, []);

  const selectReference = useCallback(
    (item: ReferenceSuggestion, setInputMessage: (msg: string) => void) => {
      const { mentionStart, query } = state;
      const mentionEnd = mentionStart + 1 + query.length;
      const before = inputMessage.slice(0, mentionStart);
      const after = inputMessage.slice(mentionEnd);
      const folderMode = query.startsWith('folder:');

      setInputMessage(before + replacementFor(item, folderMode) + after);

      const reference = toMentionReference(item);
      if (reference) {
        useChatStore.getState().addMentionReference(reference);
      }

      dismiss();
    },
    [dismiss, inputMessage, state],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!state.isOpen || state.results.length === 0) return false;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setState((prev) => ({ ...prev, selectedIndex: (prev.selectedIndex + 1) % prev.results.length }));
        return true;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setState((prev) => ({
          ...prev,
          selectedIndex: (prev.selectedIndex - 1 + prev.results.length) % prev.results.length,
        }));
        return true;
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        e.stopPropagation();
        const selected = state.results[state.selectedIndex];
        if (selected) {
          selectReference(selected, useChatStore.getState().setInputMessage);
        }
        return true;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        dismiss();
        return true;
      }
      return false;
    },
    [dismiss, selectReference, state],
  );

  return {
    isOpen: state.isOpen,
    results: state.results,
    selectedIndex: state.selectedIndex,
    query: state.query,
    selectReference,
    dismiss,
    handleKeyDown,
    hasWorkspace: !!chatId,
  };
};
