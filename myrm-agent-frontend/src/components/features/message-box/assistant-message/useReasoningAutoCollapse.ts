/**
 * [INPUT]
 * @/services/config/types::ReasoningDisplayMode (POS: Reasoning display mode setting)
 *
 * [OUTPUT]
 * useReasoningAutoCollapse: Open/closed state of the reasoning block of one answer, with the fold once the answer is in.
 *
 * [POS]
 * Owns when the reasoning accordion of an assistant message is expanded. It opens while the model is still thinking
 * and folds once, after the answer text has stopped changing for a second; a block the user opens again after that
 * fold stays open.
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
  const autoCollapsedRef = useRef(false);

  useEffect(() => {
    if (displayMode !== 'inline' && reasoning && content && isExpanded && !autoCollapsedRef.current) {
      const timer = setTimeout(() => {
        autoCollapsedRef.current = true;
        setIsExpanded(false);
      }, AUTO_COLLAPSE_DELAY_MS);
      return () => clearTimeout(timer);
    }
  }, [isExpanded, content, reasoning, displayMode]);

  return { isExpanded, toggle: () => setIsExpanded(!isExpanded) };
}
