'use client';

/**
 * [INPUT]
 * @/lib/utils/clipboardUtils::writeToClipboard (POS: shared Tauri/Web clipboard writer)
 *
 * [OUTPUT]
 * useCopyFeedback: `copy(text)` writes to the clipboard and `copied` stays true for a short confirmation window
 *
 * [POS]
 * The shared "copied" confirmation behind copy buttons; the window restarts on every copy and no timer outlives the
 * component.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

const DEFAULT_CONFIRMATION_MS = 2000;

/**
 * Copies text through the shared Tauri/Web clipboard helper and reports `copied` for a short confirmation window.
 * A repeated copy restarts the window; a refused copy leaves `copied` untouched.
 */
export function useCopyFeedback(confirmationMs = DEFAULT_CONFIRMATION_MS) {
  const [copied, setCopied] = useState(false);
  const mountedRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearTimer();
    };
  }, [clearTimer]);

  const copy = useCallback(
    async (text: string) => {
      const written = await writeToClipboard(text, true);
      if (!written || !mountedRef.current) {
        return;
      }
      clearTimer();
      setCopied(true);
      timerRef.current = setTimeout(() => setCopied(false), confirmationMs);
    },
    [clearTimer, confirmationMs],
  );

  return { copied, copy };
}
