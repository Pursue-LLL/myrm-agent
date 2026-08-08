'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { suggestReferences, type ReferenceSuggestion } from '@/services/chat';

const COVER_IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp']);

export function isCoverImageSuggestion(item: ReferenceSuggestion): boolean {
  if (item.kind !== 'file' || !item.relative_path) {
    return false;
  }
  const name = item.basename.toLowerCase();
  const dot = name.lastIndexOf('.');
  if (dot < 0) {
    return false;
  }
  return COVER_IMAGE_EXTENSIONS.has(name.slice(dot));
}

interface UseWechatCoverSuggestOptions {
  enabled: boolean;
  chatId: string | null | undefined;
  query: string;
}

export function useWechatCoverSuggest({ enabled, chatId, query }: UseWechatCoverSuggestOptions) {
  const [suggestions, setSuggestions] = useState<ReferenceSuggestion[]>([]);
  const [panelOpen, setPanelOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const requestSeqRef = useRef(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled || !chatId) {
      setPanelOpen(false);
      setSuggestions([]);
      setLoading(false);
      return;
    }

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;
    setLoading(true);
    setPanelOpen(true);

    debounceRef.current = setTimeout(() => {
      void (async () => {
        try {
          const data = await suggestReferences(chatId, query.trim(), 12, 'file');
          if (requestSeqRef.current !== requestSeq) {
            return;
          }
          setSuggestions(data.results.filter(isCoverImageSuggestion));
        } catch {
          if (requestSeqRef.current !== requestSeq) {
            return;
          }
          setSuggestions([]);
        } finally {
          if (requestSeqRef.current === requestSeq) {
            setLoading(false);
          }
        }
      })();
    }, 220);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [chatId, enabled, query]);

  const selectSuggestion = useCallback((item: ReferenceSuggestion): string | null => {
    if (!item.relative_path) {
      return null;
    }
    setPanelOpen(false);
    return item.relative_path;
  }, []);

  return {
    suggestions,
    panelOpen,
    setPanelOpen,
    loading,
    selectSuggestion,
  };
}
