/**
 * [INPUT]
 * @/store/chat/types::ChatState (POS: useChatStore 状态与操作方法契约)
 *
 * [OUTPUT]
 * extractNavigationSnapshot / getChatNavigationSnapshot / saveChatNavigationSnapshot: LRU navigation snapshot cache for sidebar chat switches.
 *
 * [POS]
 * In-memory bounded cache for instant chat re-entry when leaving a session via sidebar navigation.
 */
import type { ChatState } from '@/store/chat/types';
import {
  createEmptyPaneMessageSnapshot,
  extractChatSessionConfig,
  mergeChatSessionConfig,
} from '@/store/chat/chatSessionConfig';

const MAX_ENTRIES = 20;

const navigationSnapshots = new Map<string, Partial<ChatState>>();

export function extractNavigationSnapshot(state: ChatState): Partial<ChatState> {
  return {
    messages: state.messages,
    loading: state.loading,
    messageAppeared: state.messageAppeared,
    isMessagesLoaded: state.isMessagesLoaded,
    compactedSummary: state.compactedSummary,
    compactedBeforeId: state.compactedBeforeId,
    contextBranches: state.contextBranches,
    contextPinnedFiles: state.contextPinnedFiles,
    contextBranchesLoadError: state.contextBranchesLoadError,
    contextPinnedFilesLoadError: state.contextPinnedFilesLoadError,
    workspaceDir: state.workspaceDir,
    incognitoMode: state.incognitoMode,
    sandboxMode: state.sandboxMode,
    notFound: state.notFound,
    loadError: state.loadError,
    hideAttachList: state.hideAttachList,
    hasUsedImagesInCurrentChat: state.hasUsedImagesInCurrentChat,
    files: state.files,
    cameraFrames: state.cameraFrames,
    mentionReferences: state.mentionReferences,
    ...extractChatSessionConfig(state),
  };
}

export function resolvePaneSnapshotBase(
  chatId: string,
  paneSnapshot: Partial<ChatState> | null | undefined,
): Partial<ChatState> {
  const lruSnapshot = getChatNavigationSnapshot(chatId);
  const messageBase = createEmptyPaneMessageSnapshot();
  const withLru = lruSnapshot ? mergeChatSessionConfig(messageBase, lruSnapshot) : messageBase;
  if (!paneSnapshot) {
    return withLru;
  }
  return mergeChatSessionConfig(
    {
      ...withLru,
      ...paneSnapshot,
    },
    paneSnapshot,
  );
}

export function getChatNavigationSnapshot(chatId: string): Partial<ChatState> | null {
  const snapshot = navigationSnapshots.get(chatId);
  return snapshot ? structuredClone(snapshot) : null;
}

export function saveChatNavigationSnapshot(chatId: string, snapshot: Partial<ChatState>): void {
  if (navigationSnapshots.has(chatId)) {
    navigationSnapshots.delete(chatId);
  }
  navigationSnapshots.set(chatId, structuredClone(snapshot));

  while (navigationSnapshots.size > MAX_ENTRIES) {
    const oldestKey = navigationSnapshots.keys().next().value;
    if (!oldestKey) {
      break;
    }
    navigationSnapshots.delete(oldestKey);
  }
}

export function clearChatNavigationSnapshot(chatId: string): void {
  navigationSnapshots.delete(chatId);
}

export function resetChatNavigationSnapshotsForTests(): void {
  navigationSnapshots.clear();
}

export function getChatNavigationSnapshotCountForTests(): number {
  return navigationSnapshots.size;
}
