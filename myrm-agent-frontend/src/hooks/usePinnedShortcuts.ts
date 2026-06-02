'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import useChatStore from '@/store/useChatStore';
import { isTauri } from '@/lib/utils/clipboardUtils';

/**
 * Register global Cmd/Ctrl+1~9 shortcuts to jump to pinned chats.
 *
 * - Tauri desktop: Cmd/Ctrl + 1~9  (browser tabs don't compete)
 * - Web browser:   Cmd/Ctrl + Shift + 1~9  (avoids conflicting with browser tab shortcuts)
 */
export function usePinnedShortcuts() {
  const router = useRouter();

  useEffect(() => {
    const isTauriEnv = isTauri();

    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;

      const needsShift = !isTauriEnv;
      if (needsShift && !e.shiftKey) return;
      if (!needsShift && e.shiftKey) return;

      // Use e.code (locale-independent) instead of e.key which changes with Shift on Mac (e.g. Shift+1 = '!')
      const match = e.code.match(/^Digit([1-9])$/);
      if (!match) return;
      const digit = parseInt(match[1], 10);

      const items = useChatStore.getState().chatHistoryItems;
      const pinned = items.filter((c) => c.isPinned).sort((a, b) => (a.pinOrder ?? 0) - (b.pinOrder ?? 0));

      const target = pinned[digit - 1];
      if (!target) return;

      e.preventDefault();
      e.stopPropagation();
      router.push(`/${target.id}`);
    };

    window.addEventListener('keydown', handler, true);
    return () => window.removeEventListener('keydown', handler, true);
  }, [router]);
}
