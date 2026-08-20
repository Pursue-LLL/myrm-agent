/**
 * [INPUT]
 * @/store/chat/types::ChatState (POS: useChatStore 状态与操作方法契约)
 *
 * [OUTPUT]
 * extractChatSessionConfig / mergeChatSessionConfig: shared session-field SSOT for LRU + pane snapshots.
 *
 * [POS]
 * Keeps activeMoaPresetId and related session config consistent across sidebar LRU,
 * multi-pane background updates, and instant chat restore merges.
 */
import type { ChatState } from '@/store/chat/types';

const CHAT_SESSION_CONFIG_KEYS: ReadonlyArray<keyof ChatState> = [
  'actionMode',
  'agentConfig',
  'selectedModels',
  'hasUserSelectedModel',
  'activeMoaPresetId',
  'searchDepth',
  'incognitoMode',
  'sandboxMode',
];

export function extractChatSessionConfig(state: Partial<ChatState>): Partial<ChatState> {
  const result: Partial<ChatState> = {};
  for (const key of CHAT_SESSION_CONFIG_KEYS) {
    if (Object.prototype.hasOwnProperty.call(state, key)) {
      const value = state[key];
      if (value !== undefined) {
        (result as Record<string, unknown>)[key] = value;
      }
    }
  }
  return result;
}

export function mergeChatSessionConfig(base: Partial<ChatState>, overlay: Partial<ChatState>): Partial<ChatState> {
  return {
    ...base,
    ...extractChatSessionConfig(overlay),
  };
}

export function createEmptyPaneMessageSnapshot(): Partial<ChatState> {
  return {
    messages: [],
    loading: false,
    messageAppeared: false,
    hideAttachList: false,
    hasUsedImagesInCurrentChat: false,
  };
}
