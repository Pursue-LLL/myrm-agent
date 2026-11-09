/**
 * [INPUT]
 * @/services/config/types::ReasoningDisplayMode (POS: Reasoning display mode setting)
 *
 * [OUTPUT]
 * useReasoningAutoCollapse: Open/closed state of the reasoning block of one answer, with the fold once the answer is in.
 *
 * [POS]
 * Owns when the reasoning accordion of an assistant message is expanded. It opens while the model is still thinking
 * and folds once, after the answer text has stopped changing for a second. Only that automatic opening is folded
 * for the reader: a block the reader has toggled themselves, on a finished message or while the answer is still coming
 * in, stays as they left it.
 */

import { useEffect, useRef, useState } from 'react';
import type { ReasoningDisplayMode } from '@/services/config/types';

/** Quiet period, without a change to the answer or the reasoning, after which the block folds. */
const AUTO_COLLAPSE_DELAY_MS = 1000;

export function useReasoningAutoCollapse({
  isLast,
  loading,
  content,
  reasoning,
  displayMode,
}: {
  isLast: boolean;
  loading: boolean;
  content: string;
  reasoning: string | undefined;
  displayMode: ReasoningDisplayMode;
}): { isExpanded: boolean; toggle: () => void } {
  const [isExpanded, setIsExpanded] = useState(() => isLast && loading && !content);
  // The fold only closes a block that opened by itself while the model was thinking. The reader's first toggle makes
  // the block theirs for good, and `toggle` is the only way to open it again once it has folded.
  const toggledByReaderRef = useRef(false);

  useEffect(() => {
    if (displayMode !== 'inline' && reasoning && content && isExpanded && !toggledByReaderRef.current) {
      const timer = setTimeout(() => setIsExpanded(false), AUTO_COLLAPSE_DELAY_MS);
      return () => clearTimeout(timer);
    }
  }, [isExpanded, content, reasoning, displayMode]);

  const toggle = () => {
    toggledByReaderRef.current = true;
    setIsExpanded(!isExpanded);
  };

  return { isExpanded, toggle };
}
