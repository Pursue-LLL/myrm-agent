/**
 * [INPUT]
 * @/store/chat/types::ChatState, Message, File, AgentConfig, ActionMode, BuiltinToolId, MentionReference (POS: Chat store type contract)
 *
 * [OUTPUT]
 * ChatActionsState: The chat store state the send, request and attach pipeline reads.
 * ChatActionsMethods: The chat store actions the send and attach pipeline calls.
 *
 * [POS]
 * Contract between the chat store and the message request pipeline: the store hands both to sendMessage / attachToChat.
 */

import type {
  ActionMode,
  AgentConfig,
  BuiltinToolId,
  ChatState,
  File,
  MentionReference,
  Message,
} from '@/store/chat/types';

export interface ChatActionsState {
  chatId: string | undefined;
  actionMode: ActionMode;
  searchDepth: 'normal' | 'deep';
  agentConfig: AgentConfig | null;
  abortController: AbortController | null;
  loading: boolean;
  loadingOlder: boolean;
  messages: Message[];
  compactedSummary: string | null;
  compactedBeforeId: string | null;
  files: File[];
  mentionReferences: MentionReference[];
  visionFrames: string[];
  hideAttachList: boolean;
  hasUsedImagesInCurrentChat: boolean;
  isGoalMode: boolean;
  goalBudgetTokens: number | null;
  goalBudgetUsd: number | null;
  goalMaxTimeSeconds: number | null;
  goalMaxTurns: number | null;
  goalProtectedPaths: string[] | null;
  goalLoopOnPause: boolean;
  goalConvergenceWindow: number | null;
  goalAcceptanceCriteria: Array<Record<string, unknown>> | null;
  goalConstraints: string[] | null;
  goalCheckpointMode: boolean;
  isWorkflowMode: boolean;
  currentSessionMessageId: string | null;
  messageAppeared: boolean;
  isMessagesLoaded: boolean;
  hasMoreMessages: boolean;
  nextCursor: string | null;
  incognitoMode: boolean;
  securityPreset: import('./types/chatState').SecurityPreset;
  notFound: boolean;
  loadError: boolean;
  newChatCreated: boolean;
  currentBuiltinTools: BuiltinToolId[];
  activeMoaPresetId: string | null;
  lastCompactionMeta: import('./types/messages').LastCompactionMeta | null;
  sessionSkillOverrides: string[] | null;
  sessionAccessRoots: import('./types/sessionAccess').SessionAccessRoot[];
  contextBranches: import('./types/chatState').ChatState['contextBranches'];
  contextPinnedFiles: string[];
  contextBranchesLoadError: string | null;
  contextPinnedFilesLoadError: string | null;
  activeKnowledgeBaseIds: string[];
  activeKnowledgeBaseNames: Record<string, string>;
  regenerateSiblingGroupId?: string;
  regenerateInstruction?: string;
  clearMentionReferences: () => void;
}

export interface ChatActionsMethods {
  setMessages: (updater: (state: ChatState) => void) => void;
  setLoading: (loading: boolean) => void;
  /** Clear terminal stream state without aborting the already-completed transport. */
  clearActiveStream?: () => void;
  setMessageAppeared: (appeared: boolean) => void;
  setHideAttachList: (hide: boolean) => void;
  setHasUsedImagesInCurrentChat: (hasUsed: boolean) => void;
  setIsWorkflowMode: (enabled: boolean) => void;
  clearPendingWorkflowTemplate: () => void;
  setSelectedModels: (models: { base: string | null; vision: string | null; reasoning: string | null }) => void;
  setHasUserSelectedModel: (hasSelected: boolean) => void;
  clearCurrentSessionMessageId: () => void;
  _processSuggestions: (lastMsg: Message) => Promise<void>;
  scheduleAutoSave: () => void;
  setInputMessage: (message: string) => void;
}
