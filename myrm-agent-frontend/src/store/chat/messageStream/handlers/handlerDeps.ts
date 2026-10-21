/**
 * [POS]
 * Shared imports for messageStream handler slices (avoids duplicating large import blocks).
 */

export { AgentEventType } from '@/store/chat/types';
export type {
  Source,
  File,
  AgentStreamEvent,
  Artifact,
  ArtifactType,
  AsyncUserMessageEntry,
  ClarificationForm,
  ClarificationOption,
  ClarificationQuestion,
  ErrorKind,
  FissionTopologyUpdateStreamEvent,
  GoalStatusPayload,
  ProgressItem,
  Message,
  ToolApprovalRequest,
} from '@/store/chat/types';
export {
  buildArchiveRestoreActions,
  parseArchiveRestoreBlockPayload,
  parseArchiveRestoreResultPayload,
} from '../../archiveRestoreActions';
export {
  findAssistantMessageIndex,
  ensureAssistantStreamMessage,
  clearAssistantDraft,
  discardStreamedDraft,
} from '../../messageUtils';
export {
  isMemoryRecallToolName,
  mergeCitedMemoryReferences,
  normalizeCitedMemoryReferences,
} from '../../memoryCitationUtils';
export { default as useArtifactPortalStore } from '@/store/useArtifactPortalStore';
export { default as useToolApprovalStore } from '@/store/useToolApprovalStore';
export { default as useToolsSnapshotStore } from '@/store/useToolsSnapshotStore';
export { useChatStore };
export { default as useConfigStore } from '@/store/useConfigStore';
export { playCompletionSound } from '@/lib/utils/completionSound';
export { dispatchPetSurfaceAwayCompletion } from '@/components/features/companion/sprite/petSurfaceAwayCompletion';
import useChatStore from '@/store/useChatStore';
import type { SubagentStore } from '@/store/chat/useSubagentStore';
import type { StreamHandlerState } from '../types';
export type { ProgressFileItem } from '../types';
export {
  getContextOverflowMessage,
  getUserFriendlyError,
  mapTaskStepStatus,
  mergeMessageSources,
  normalizeClarificationForm,
  normalizeGoalState,
  resolveClarifyIsResumeMode,
} from '../streamHelpers';
export { parseProgressFilePath, pathsMatchForFileDiff, pickMergedFileDiffPayload } from '../fileDiffMerge';
export { sanitizeStreamText } from '../textSanitize';

/**
 * Fire-and-forget release of desktop + browser inspector "controlling" state for the
 * turn owned by chatId. Terminal paths (ERROR / AGENT_CANCELLED / CONTEXT_OVERFLOW_RESET /
 * GOAL_STATUS budget_limited / MESSAGE_END) share this lazy wrapper instead of inlining
 * the dynamic import; releaseTurnEngagement returns ownership for the ending turn and
 * reclaims its viewData even if another pane overwrote the engagement slot, while viewData
 * owned by another chat / a manually opened panel is preserved, so parallel panes are
 * never force-closed and no ghost control lingers. Chunk load failure is swallowed so the
 * stop/turn path never surfaces an unhandled rejection.
 */
export function releaseInspectorControls(chatId: string): void {
  void import('@/lib/inspector/releaseTurnInspectorControls')
    .then(({ releaseTurnInspectorControls }) => releaseTurnInspectorControls(chatId))
    .catch(() => undefined);
}

/**
 * Resolve the chatId that owns the current stream. Prefers the chatId captured at
 * send time; falls back to messages[0].chatId for streams built without a chatId
 * (tests, legacy callers). Without this, a brand-new chat's first turn would
 * resolve an empty chatId and silently no-op inspector engagement/release.
 */
export function resolveStreamChatId(state: StreamHandlerState): string {
  return state.chatId?.trim() || state.messages[0]?.chatId?.trim() || '';
}

/**
 * Whether the stream belongs to the chat the user has open. Several chats can stream at once, but the single-slot
 * stores (subagent tree, fission strip) describe only the open chat; a stream that cannot name its chat, or a store
 * that holds no chat id yet, is never "the open chat".
 */
export function isStreamForOpenChat(state: StreamHandlerState): boolean {
  const streamChatId = resolveStreamChatId(state);
  return streamChatId !== '' && streamChatId === (useChatStore.getState().chatId?.trim() ?? '');
}

/**
 * Applies a write to the subagent store while the stream's chat is still the open one. The store loads lazily, so the
 * check runs once the chunk has arrived: a chat switch that happened while it loaded drops the write instead of
 * landing it in the next chat's tree.
 */
export function writeSubagentStore(state: StreamHandlerState, write: (store: SubagentStore) => void): void {
  void import('@/store/chat/useSubagentStore').then(({ useSubagentStore }) => {
    if (isStreamForOpenChat(state)) {
      write(useSubagentStore.getState());
    }
  });
}
