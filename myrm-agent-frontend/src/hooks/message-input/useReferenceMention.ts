/**
 * @ reference autocomplete hook.
 *
 * [INPUT]
 * - @/services/chat::suggestReferences (POS: Server-side safe reference suggestions)
 * - @/services/chat::searchCitableChats (POS: Prior conversation citable search)
 * - ./useReferenceMentionUtils (POS: Reference extraction, formatting and suggestion builders)
 * - @/store/useChatStore (POS: Global chat state, selection and input update)
 * - @/store/useAgentStore (POS: Digital employee registry prefetch)
 *
 * [OUTPUT]
 * - useReferenceMention: hook providing reference mention state, keyboard nav and selection.
 *
 * [POS]
 * Chat input @ reference autocomplete. Guarantees immediate, responsive digital employee
 * (@Agent) discovery on both EmptyChat and active sessions across WebUI, Tauri, and Cloud.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocale } from 'next-intl';
import { suggestReferences, searchCitableChats, type ReferenceSuggestion } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import useAgentStore from '@/store/useAgentStore';
import {
  type ReferenceMentionState,
  DEBOUNCE_MS,
  extractMentionQuery,
  staticSpecialMatches,
  buildAgentSuggestions,
  historyResultToSuggestion,
  toMentionReference,
  replacementFor,
} from './useReferenceMentionUtils';

export { type ReferenceMentionState } from './useReferenceMentionUtils';

export const useReferenceMention = (inputMessage: string, cursorPosition: number) => {
  const locale = useLocale();
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
    const chatMode = !folderMode && !wikiMode && mention.query.startsWith('chat:');
    const query = folderMode
      ? mention.query.slice('folder:'.length)
      : wikiMode
        ? mention.query.slice('wiki:'.length)
        : chatMode
          ? mention.query.slice('chat:'.length)
          : mention.query;

    const specialResults = folderMode || wikiMode || chatMode ? [] : staticSpecialMatches(mention.query);
    const initialAgentResults = folderMode || wikiMode || chatMode ? [] : buildAgentSuggestions(query, locale);

    // Synchronously open menu with instant local agents and special commands (eliminates EmptyChat lag)
    setState((prev) => ({
      ...prev,
      isOpen: true,
      query: mention.query,
      mentionStart: mention.start,
      selectedIndex: 0,
      results: folderMode || wikiMode || chatMode ? specialResults : [...initialAgentResults, ...specialResults],
    }));

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;

    if (chatMode) {
      debounceRef.current = setTimeout(async () => {
        try {
          const data = await searchCitableChats(query, 20, 0, chatId ?? undefined);
          if (requestSeqRef.current !== requestSeq) {
            return;
          }
          const seen = new Set<string>();
          const chatResults = data.items
            .filter((item) => {
              if (seen.has(item.chat_id)) {
                return false;
              }
              seen.add(item.chat_id);
              return !chatId || item.chat_id !== chatId;
            })
            .map(historyResultToSuggestion);
          setState((prev) => ({
            ...prev,
            results: chatResults,
            selectedIndex: 0,
          }));
        } catch {
          if (requestSeqRef.current !== requestSeq) {
            return;
          }
          setState((prev) => ({ ...prev, results: [], selectedIndex: 0 }));
        }
      }, DEBOUNCE_MS);
      return () => {
        if (debounceRef.current) {
          clearTimeout(debounceRef.current);
        }
      };
    }

    // Debounce server workspace & wiki suggestions
    debounceRef.current = setTimeout(async () => {
      const currentAgentResults = folderMode || wikiMode || chatMode ? [] : buildAgentSuggestions(query, locale);

      if (!chatId) {
        // EmptyChat mode: No remote workspace files yet, but digital employees and static commands are 100% active
        if (requestSeqRef.current === requestSeq) {
          setState((prev) => ({
            ...prev,
            results: folderMode || wikiMode ? [] : [...currentAgentResults, ...specialResults],
            selectedIndex: 0,
          }));
        }
        return;
      }

      try {
        const data = await suggestReferences(chatId, query, 30, folderMode ? 'directory' : 'any');
        if (requestSeqRef.current !== requestSeq) {
          return;
        }
        const serverResults = folderMode
          ? data.results
          : wikiMode
            ? data.results.filter((item) => item.source === 'wiki')
            : data.results.filter((item) => item.source !== 'special');

        setState((prev) => ({
          ...prev,
          results: folderMode || wikiMode ? serverResults : [...currentAgentResults, ...specialResults, ...serverResults],
          selectedIndex: 0,
        }));
      } catch {
        if (requestSeqRef.current !== requestSeq) {
          return;
        }
        setState((prev) => ({
          ...prev,
          results: folderMode || wikiMode ? [] : [...currentAgentResults, ...specialResults],
          selectedIndex: 0,
        }));
      }
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [chatId, cursorPosition, inputMessage, locale]);

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
        useChatStore.getState().addMentionReference({ ...reference, viaText: true });
      }

      dismiss();
    },
    [dismiss, inputMessage, state],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!state.isOpen || state.results.length === 0) {
        return false;
      }
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
