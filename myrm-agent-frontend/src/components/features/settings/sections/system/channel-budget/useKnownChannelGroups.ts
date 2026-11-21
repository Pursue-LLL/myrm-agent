'use client';

/**
 * [INPUT]
 * - react::useCallback, useRef, useState (POS: React core hooks)
 * - @/services/budget (POS: Channel budget API service)
 * - ./useChannelBudgets::LoadStatus (POS: Where a load from the server stands)
 *
 * [OUTPUT]
 * - useKnownChannelGroups: the budget keys of the groups that have a chat, how the last load went, and `load` to ask again
 *
 * [POS]
 * Candidates of the add form's picker. Asked each time the form is opened, because chats appear while the page stays
 * open; only the newest answer lands. A failed load leaves the picker out instead of raising a notice: typing the key
 * still works.
 */

import { useCallback, useRef, useState } from 'react';
import { getKnownChannelGroups } from '@/services/budget';
import type { LoadStatus } from './useChannelBudgets';

export function useKnownChannelGroups() {
  const [channelKeys, setChannelKeys] = useState<string[]>([]);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const latest = useRef(0);

  /** Reads the groups again; never throws, and keeps the groups on screen until the answer is in. */
  const load = useCallback(async () => {
    const request = ++latest.current;
    // The request is silent: a failed load only leaves the picker out.
    const answer = await getKnownChannelGroups().catch(() => null);
    if (request !== latest.current) {
      return;
    }
    if (answer) {
      setChannelKeys(answer.channel_keys);
      setStatus('ready');
    } else {
      setStatus('failed');
    }
  }, []);

  return { channelKeys, status, load };
}
