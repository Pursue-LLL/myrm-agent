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
 *   and when a turn ends while the user is looking
 *
 * [POS]
 * Keeps the Catchup inbox honest: a reply the user watched arrive is never listed as unseen.
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

    const stamp = () => {
      if (!isUserPresent()) {
        return;
      }
      // Presence is best effort; a missed stamp only leaves a chat listed in the inbox a little longer.
      markChatAsRead(chatId, { silent: true }).catch(() => undefined);
    };

    const onRunDigest = (event: Event) => {
      const detail = (event as CustomEvent<RunDigestEventDetail>).detail;
      if (detail?.chat_id === chatId && TERMINAL_PHASES.has(detail.digest?.phase ?? '')) {
        stamp();
      }
    };

    stamp();
    window.addEventListener('focus', stamp);
    document.addEventListener('visibilitychange', stamp);
    window.addEventListener('run-digest-updated', onRunDigest);
    return () => {
      window.removeEventListener('focus', stamp);
      document.removeEventListener('visibilitychange', stamp);
      window.removeEventListener('run-digest-updated', onRunDigest);
    };
  }, [chatId, hasContent]);
}
