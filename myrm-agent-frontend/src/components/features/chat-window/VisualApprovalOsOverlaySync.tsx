'use client';

/**
 * [INPUT]
 * - @/store/useChatStore, useToolApprovalStore, inspector stores
 * - @/hooks/useVisualApprovalOsOverlay
 *
 * [OUTPUT]
 * - VisualApprovalOsOverlaySync: mounts Tauri OS overlay sync for active chat
 *
 * [POS]
 * Chat-level mount point for §7 native visual approval overlay.
 */

import { useMemo } from 'react';

import { useVisualApprovalOsOverlay } from '@/hooks/useVisualApprovalOsOverlay';
import { useVisualApprovalSnapshot } from '@/hooks/useVisualApprovalSnapshot';
import { partitionApprovalQueue } from '@/lib/approval/visualApprovalSurface';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useChatStore from '@/store/useChatStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';

export default function VisualApprovalOsOverlaySync() {
  const chatId = useChatStore((state) => state.chatId);
  const queue = useToolApprovalStore((state) => state.queue);
  const desktopViewData = useDesktopInspectorStore((state) => state.viewData);
  const browserViewData = useBrowserInspectorStore((state) => state.viewData);
  const desktopLoading = useDesktopInspectorStore((state) => state.isSnapshotLoading);
  const browserLoading = useBrowserInspectorStore((state) => state.isSnapshotLoading);

  const inlineRequests = useMemo(() => {
    if (!chatId) {
      return [];
    }

    const chatQueue = queue.filter((request) => request.chatId === chatId);
    return partitionApprovalQueue(chatQueue).inlineRequests;
  }, [chatId, queue]);

  const { snapshotFetchFailed } = useVisualApprovalSnapshot(inlineRequests);

  useVisualApprovalOsOverlay(
    inlineRequests,
    desktopViewData,
    browserViewData,
    desktopLoading,
    browserLoading,
    snapshotFetchFailed,
  );

  return null;
}
