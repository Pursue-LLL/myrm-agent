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
    workspaceDir: state.workspaceDir,
    incognitoMode: state.incognitoMode,
    sandboxMode: state.sandboxMode,
    notFound: state.notFound,
    loadError: state.loadError,
    hideAttachList: state.hideAttachList,
    hasUsedImagesInCurrentChat: state.hasUsedImagesInCurrentChat,
    actionMode: state.actionMode,
    agentConfig: state.agentConfig,
    selectedModels: state.selectedModels,
    hasUserSelectedModel: state.hasUserSelectedModel,
    files: state.files,
    cameraFrames: state.cameraFrames,
    mentionReferences: state.mentionReferences,
  };
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
