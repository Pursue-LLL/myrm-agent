'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import useChatStore from '@/store/useChatStore';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import { isTauri } from '@/lib/utils/clipboardUtils';

/**
 * Register global keyboard shortcuts for the application.
 *
 * Platform-aware modifier handling:
 * - Tauri desktop: Cmd/Ctrl + key  (no browser tab conflicts)
 * - Web browser:   Cmd/Ctrl + Shift + key  (avoids browser-native shortcuts)
 *
 * Shortcuts:
 * - Cmd/Ctrl + N:   Create new chat
 * - Cmd/Ctrl + B:   Toggle Browser LiveView panel
 * - Cmd/Ctrl + 1~9: Jump to pinned chat by position
 */
export function useGlobalShortcuts() {
  const router = useRouter();

  useEffect(() => {
    const isTauriEnv = isTauri();

    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;

      const needsShift = !isTauriEnv;
      if (needsShift && !e.shiftKey) return;
      if (!needsShift && e.shiftKey) return;

      if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        e.stopPropagation();
        useChatStore.getState().initializeChat(undefined);
        router.push('/');
        return;
      }

      if (e.key === 'b' || e.key === 'B') {
        e.preventDefault();
        e.stopPropagation();
        const inspector = useBrowserInspectorStore.getState();
        inspector.togglePanel();
        if (!inspector.isOpen) void inspector.fetchSnapshot();
        return;
      }

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
