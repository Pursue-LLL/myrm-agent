'use client';

/**
 * Stamps the user's presence in the open chat.
 *
 * [INPUT]
 * - services/chat::markChatAsRead (POS: records presence server-side)
 * - lib/utils/userPresence::isUserPresent (POS: visible-and-focused page check)
 * - window event `run-digest-updated` (POS: turn phase changes from the global SSE bridge)
 *
 * [OUTPUT]
 * - usePresenceReadMark: stamp when the chat opens with content, when the window comes back to the foreground,
 *   when a turn ends while the user is looking, and when the user stops looking (window blur, page hidden,
 *   leaving the chat)
 *
 * [POS]
 * Keeps the Catchup inbox honest: everything the user watched arrive is never listed as unseen, including replies
 * that reach the page without a turn-end event (background sub-agent wakeups, a dropped event stream).
 */

import { useEffect } from 'react';
import { isUserPresent } from '@/lib/utils/userPresence';
import { markChatAsRead } from '@/services/chat';

const TERMINAL_PHASES: ReadonlySet<string> = new Set(['completed', 'error', 'cancelled']);

interface RunDigestEventDetail {
  chat_id?: string;
  digest?: { phase?: string };
}

/**
 * @param chatId Open chat; empty when none.
 * @param hasContent Whether the chat holds messages. A chat the server has not stored yet has nothing to stamp.
 */
export function usePresenceReadMark(chatId: string, hasContent: boolean): void {
  useEffect(() => {
    if (!chatId || !hasContent) {
      return;
    }

    // Presence is best effort; a missed stamp only leaves a chat listed in the inbox a little longer.
    const stamp = () => {
      markChatAsRead(chatId, { silent: true }).catch(() => undefined);
    };

    // The page has already lost focus by the time blur or hidden fires, so presence is tracked across events:
    // only the first of them stamps, and a hide after a blur does not claim replies that arrived in between.
    let present = isUserPresent();

    const stampIfPresent = () => {
      if (isUserPresent()) {
        present = true;
        stamp();
      }
    };

    const onAway = () => {
      if (present) {
        present = false;
        stamp();
      }
    };

    const onVisibilityChange = () => (document.hidden ? onAway() : stampIfPresent());

    const onRunDigest = (event: Event) => {
      const detail = (event as CustomEvent<RunDigestEventDetail>).detail;
      if (detail?.chat_id === chatId && TERMINAL_PHASES.has(detail.digest?.phase ?? '') && isUserPresent()) {
        stamp();
      }
    };

    if (present) {
      stamp();
    }
    window.addEventListener('focus', stampIfPresent);
    window.addEventListener('blur', onAway);
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('run-digest-updated', onRunDigest);
    return () => {
      window.removeEventListener('focus', stampIfPresent);
      window.removeEventListener('blur', onAway);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('run-digest-updated', onRunDigest);
      // Leaving the chat while looking at the page; a page that is already away was stamped by onAway.
      if (isUserPresent()) {
        stamp();
      }
    };
  }, [chatId, hasContent]);
}
