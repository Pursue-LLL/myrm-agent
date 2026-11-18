/**
 * @ reference autocomplete hook.
 *
 * [INPUT]
 * - @/services/chat::suggestReferences (POS: Server-side safe reference suggestions)
 * - @/services/chatHistorySearch::searchCitableChats (POS: Prior conversation citable search)
 * - ./useReferenceMentionUtils (POS: Mention planning, reference formatting and suggestion builders)
 * - @/store/useChatStore (POS: Global chat state, selection and input update)
 * - @/store/useAgentStore (POS: Digital employee registry prefetch)
 *
 * [OUTPUT]
 * - useReferenceMention: hook providing reference mention state (incl. whether a server search is still open), keyboard nav and selection.
 *
 * [POS]
 * Chat input @ reference autocomplete. Guarantees immediate, responsive digital employee
 * (@Agent) discovery on both EmptyChat and active sessions across WebUI, Tauri, and Cloud.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocale } from 'next-intl';
import { suggestReferences, type ReferenceSuggestion } from '@/services/chat';
import { searchCitableChats } from '@/services/chatHistorySearch';
import useChatStore from '@/store/useChatStore';
import useAgentStore from '@/store/useAgentStore';
import {
  type MentionPlan,
  type ReferenceMentionState,
  DEBOUNCE_MS,
  buildAgentSuggestions,
  historyResultToSuggestion,
  planMention,
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
    isSearching: false,
  });
  const chatId = useChatStore((s) => s.chatId);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestSeqRef = useRef(0);

  useEffect(() => {
    void useAgentStore.getState().fetchAgents();
  }, []);

  const plan = useMemo(
    () => planMention(inputMessage, cursorPosition, locale, chatId ?? undefined),
    [chatId, cursorPosition, inputMessage, locale],
  );
  // The menu opens, reshapes or closes in the render that sees the new text, with the loaded agents and commands
  // already in it (no EmptyChat lag), so no frame shows the previous mention's menu. The plan last applied is kept to
  // tell a new plan from one already shown.
  const [appliedPlan, setAppliedPlan] = useState<MentionPlan | null>(null);
  if (plan !== appliedPlan) {
    setAppliedPlan(plan);
    setState((prev) => {
      if (!plan) {
        return prev.isOpen ? { ...prev, isOpen: false, results: [], selectedIndex: 0, isSearching: false } : prev;
      }
      return {
        ...prev,
        isOpen: true,
        query: plan.rawQuery,
        mentionStart: plan.start,
        selectedIndex: 0,
        isSearching: plan.willSearch,
        results: plan.localResults,
      };
    });
  }

  useEffect(() => {
    if (!plan) {
      return;
    }
    const { mode, query, specialResults } = plan;

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;

    if (mode === 'chat') {
      if (!query) {
        return;
      }
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
            isSearching: false,
          }));
        } catch {
          if (requestSeqRef.current !== requestSeq) {
            return;
          }
          setState((prev) => ({ ...prev, results: [], selectedIndex: 0, isSearching: false }));
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
      const currentAgentResults = mode === 'plain' ? buildAgentSuggestions(query, locale) : [];

      if (!chatId) {
        // EmptyChat mode: No remote workspace files yet, but digital employees and static commands are 100% active
        if (requestSeqRef.current === requestSeq) {
          setState((prev) => ({
            ...prev,
            results: mode === 'plain' ? [...currentAgentResults, ...specialResults] : [],
            selectedIndex: 0,
          }));
        }
        return;
      }

      try {
        const data = await suggestReferences(chatId, query, 30, mode === 'folder' ? 'directory' : 'any');
        if (requestSeqRef.current !== requestSeq) {
          return;
        }
        const serverResults =
          mode === 'folder'
            ? data.results
            : mode === 'wiki'
              ? data.results.filter((item) => item.source === 'wiki')
              : data.results.filter((item) => item.source !== 'special');

        setState((prev) => ({
          ...prev,
          results: mode === 'plain' ? [...currentAgentResults, ...specialResults, ...serverResults] : serverResults,
          selectedIndex: 0,
          isSearching: false,
        }));
      } catch {
        if (requestSeqRef.current !== requestSeq) {
          return;
        }
        setState((prev) => ({
          ...prev,
          results: mode === 'plain' ? [...currentAgentResults, ...specialResults] : [],
          selectedIndex: 0,
          isSearching: false,
        }));
      }
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [chatId, locale, plan]);

  const dismiss = useCallback(() => {
    setState((prev) => ({ ...prev, isOpen: false, results: [], selectedIndex: 0, isSearching: false }));
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
    isSearching: state.isSearching,
    selectReference,
    dismiss,
    handleKeyDown,
    hasWorkspace: !!chatId,
  };
};
