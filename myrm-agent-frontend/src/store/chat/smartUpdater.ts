/**
 * [INPUT]
 * @/store/useWorkspaceStore::useWorkspaceStore (POS: Multi-pane workspace store holding per-pane snapshots)
 * @/store/chat/chatNavigationSnapshotCache::resolvePaneSnapshotBase (POS: Base snapshot of a background pane)
 *
 * [OUTPUT]
 * createSmartUpdater: Route state updates to the active store or a background pane snapshot.
 *
 * [POS]
 * MMU of the chat stream: a turn keeps writing to its own chat even after the user switched panes.
 */

import { produce } from 'immer';
import { resolvePaneSnapshotBase } from '@/store/chat/chatNavigationSnapshotCache';
import type { ChatState } from '@/store/chat/types';
import useWorkspaceStore, { type PaneConfig } from '../useWorkspaceStore';

export const createSmartUpdater = (
  chatId: string | undefined,
  originalSetMessages: (updater: (state: ChatState) => void) => void,
) => {
  return (updater: (state: ChatState) => void) => {
    if (!chatId) {
      originalSetMessages(updater);
      return;
    }

    const workspaceState = useWorkspaceStore.getState();
    if (workspaceState.panes.length === 0) {
      originalSetMessages(updater);
      return;
    }

    const activePane = workspaceState.panes.find((p: PaneConfig) => p.id === workspaceState.activePaneId);

    if (activePane && activePane.chatId === chatId) {
      originalSetMessages(updater);
      return;
    }

    const pane = workspaceState.panes.find((p: PaneConfig) => p.chatId === chatId);
    if (pane) {
      const currentSnapshot = resolvePaneSnapshotBase(chatId, pane.snapshot ?? null);
      const nextSnapshot = produce(currentSnapshot, (draft: ChatState) => {
        updater(draft);
      });
      useWorkspaceStore.getState().savePaneSnapshot(pane.id, nextSnapshot);
      return;
    }

    originalSetMessages(updater);
  };
};
