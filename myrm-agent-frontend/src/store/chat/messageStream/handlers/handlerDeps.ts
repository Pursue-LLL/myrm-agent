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
  UIArtifact,
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
  findUiArtifactLocation,
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
export { default as useChatStore } from '@/store/useChatStore';
export { default as useConfigStore } from '@/store/useConfigStore';
export { playCompletionSound } from '@/lib/utils/completionSound';
export { dispatchPetSurfaceAwayCompletion } from '@/components/features/companion/sprite/petSurfaceAwayCompletion';
export type { ProgressFileItem } from '../types';
export {
  getContextOverflowMessage,
  getUserFriendlyError,
  mapTaskStepStatus,
  mergeMessageSources,
  normalizeClarificationForm,
  normalizeGoalState,
  normalizeSubagentStatus,
} from '../streamHelpers';
export {
  parseProgressFilePath,
  pathsMatchForFileDiff,
  pickMergedFileDiffPayload,
} from '../fileDiffMerge';
export { sanitizeStreamText } from '../textSanitize';

/**
 * Fire-and-forget release of desktop + browser inspector "controlling" state for the
 * turn owned by chatId. Terminal paths (ERROR / AGENT_CANCELLED / CONTEXT_OVERFLOW_RESET /
 * GOAL_STATUS budget_limited / MESSAGE_END) share this lazy wrapper instead of inlining
 * the dynamic import; releaseTurnEngagement is a no-op for other chats / manually opened
 * panels, so parallel panes are never force-closed. Chunk load failure is swallowed so the
 * stop/turn path never surfaces an unhandled rejection.
 */
export function releaseInspectorControls(chatId: string): void {
  void import('@/lib/inspector/releaseTurnInspectorControls')
    .then(({ releaseTurnInspectorControls }) => releaseTurnInspectorControls(chatId))
    .catch(() => undefined);
}
