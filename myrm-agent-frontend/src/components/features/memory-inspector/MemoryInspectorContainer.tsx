/**
 * Global Host Container for Memory Inspector Drawer.
 *
 * [INPUT] useMemoryInspectorStore
 * [OUTPUT] MemoryInspectorContainer Component
 * [POS] Item 30 host-level drawer container. Strictly under 120 lines. Zero `any`.
 */

import React, { useCallback, useEffect } from 'react';
import { useMemoryInspectorStore } from '@/store/useMemoryInspectorStore';
import { MemoryInspectorDrawer } from './MemoryInspectorDrawer';
import type { EpistemicMemoryItem } from './memoryInspectorTypes';

export const MemoryInspectorContainer: React.FC = () => {
  const isOpen = useMemoryInspectorStore((state) => state.isOpen);
  const sessionId = useMemoryInspectorStore((state) => state.sessionId);
  const memories = useMemoryInspectorStore((state) => state.memories);
  const closeInspector = useMemoryInspectorStore((state) => state.closeInspector);
  const promoteMemory = useMemoryInspectorStore((state) => state.promoteMemory);
  const correctMemory = useMemoryInspectorStore((state) => state.correctMemory);
  const forgetMemory = useMemoryInspectorStore((state) => state.forgetMemory);
  const openInspector = useMemoryInspectorStore((state) => state.openInspector);

  // Listen to global open event
  useEffect(() => {
    const handleOpenEvent = (event: Event) => {
      const customEvent = event as CustomEvent<{ sessionId: string; memories: EpistemicMemoryItem[] }>;
      if (customEvent.detail) {
        openInspector(customEvent.detail.sessionId, customEvent.detail.memories);
      }
    };

    window.addEventListener('myrm:open-memory-inspector', handleOpenEvent);
    return () => {
      window.removeEventListener('myrm:open-memory-inspector', handleOpenEvent);
    };
  }, [openInspector]);

  const handlePromote = useCallback(
    async (memoryId: string, targetTier?: 'assertion' | 'observation') => {
      await promoteMemory(memoryId, targetTier);
    },
    [promoteMemory]
  );

  const handleCorrect = useCallback(
    async (memoryId: string, newContent: string) => {
      await correctMemory(memoryId, newContent);
    },
    [correctMemory]
  );

  const handleForget = useCallback(
    async (memoryId: string) => {
      await forgetMemory(memoryId);
    },
    [forgetMemory]
  );

  if (!isOpen) {
    return null;
  }

  return (
    <MemoryInspectorDrawer
      isOpen={isOpen}
      onClose={closeInspector}
      memories={memories}
      sessionId={sessionId}
      onPromote={handlePromote}
      onCorrect={handleCorrect}
      onForget={handleForget}
    />
  );
};
