'use client';

/**
 * [INPUT]
 * - react::useEffect, useSyncExternalStore
 *
 * [OUTPUT]
 * - useNoticeSlot: whether a notice may be on screen now; only one notice holds the slot at a time.
 * - NoticeId: the notices that compete for the slot.
 *
 * [POS]
 * Keeps the cards above an empty chat's sample prompts from stacking. Each card learns it has something to say at
 * its own moment (a disk scan, a network probe), so without coordination a late card is inserted above one that is
 * already readable and pushes the whole page down. The notice that asks first keeps the slot until it is closed or
 * unmounted; the others wait their turn instead of appearing next to it.
 */

import { useEffect, useSyncExternalStore } from 'react';

export type NoticeId = 'migration-discovery' | 'update-nudge';

/** Notices that want to be shown, oldest first; the head holds the slot. */
const queue: NoticeId[] = [];
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function notify(): void {
  listeners.forEach((listener) => listener());
}

/** `wantsSlot` is true from the moment the notice has content to show until it is closed. */
export function useNoticeSlot(id: NoticeId, wantsSlot: boolean): boolean {
  useEffect(() => {
    if (!wantsSlot) {
      return;
    }
    queue.push(id);
    notify();
    return () => {
      const position = queue.indexOf(id);
      if (position !== -1) {
        queue.splice(position, 1);
      }
      notify();
    };
  }, [id, wantsSlot]);

  return useSyncExternalStore(
    subscribe,
    () => queue[0] === id,
    () => false,
  );
}
