'use client';

/**
 * [INPUT]
 * - @/hooks/ui/persistedStringStore::createPersistedStringStore (POS: per-device key → string memory with change notifications)
 *
 * [OUTPUT]
 * - useComposerOptionsOpen: whether the viewer keeps the composer's options region open, with its setter.
 *
 * [POS]
 * The region starts closed. A viewer who opens it finds it open again on the next chat and the next visit.
 * The server and the hydration render report "closed", then the stored choice applies without a mismatch.
 */

import { useCallback, useSyncExternalStore } from 'react';

import { createPersistedStringStore } from '@/hooks/ui/persistedStringStore';

const OPEN_KEY = 'optionsOpen';
const OPEN = '1';
const CLOSED = '0';

const store = createPersistedStringStore('myrm.composer.');

export function useComposerOptionsOpen(): readonly [boolean, (open: boolean) => void] {
  const open = useSyncExternalStore(
    store.subscribe,
    () => store.read(OPEN_KEY) === OPEN,
    () => false,
  );
  const setOpen = useCallback((next: boolean) => store.write(OPEN_KEY, next ? OPEN : CLOSED), []);
  return [open, setOpen] as const;
}
