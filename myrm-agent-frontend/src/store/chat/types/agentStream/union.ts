/**
 * [INPUT]
 * ./part1, ./part2, ./part3 导出的事件接口 (POS: SSE 分片)
 *
 * [OUTPUT]
 * AgentStreamEvent 联合类型。
 *
 * [POS]
 * 全部 SSE 事件的 discriminated union。
 */

import type { AgentCancelledStreamEvent } from './part1';
import type {
  ApprovalRequiredStreamEvent,
  ArtifactContentStreamEvent,
  ArtifactFocusStreamEvent,
  ArtifactsStreamEvent,
  AsyncUserMessageStreamEvent,
  ClarificationRequiredStreamEvent,
  CapabilityGapStreamEvent,
  SkillGapStreamEvent,
  PhaseTransitionStreamEvent,
  ErrorStreamEvent,
  MessageStreamEvent,
  RateLimitThrottledStreamEvent,
  RateLimitUpdatedStreamEvent,
  RateLimitWarningStreamEvent,
  RedirectedStreamEvent,
  RiskBlockedStreamEvent,
  SessionRecordingStreamEvent,
  SourcesStreamEvent,
  SteeringStreamEvent,
  TasksStepsStreamEvent,
  TokenUsageStreamEvent,
  ToolApprovalRequestStreamEvent,
  ToolCancelledStreamEvent,
  ToolEvictedRefStreamEvent,
  ToolEndStreamEvent,
  ToolFailureStreamEvent,
  ToolHeartbeatStreamEvent,
  ToolStartStreamEvent,
  ToolStdoutChunkStreamEvent,
  UIUpdateStreamEvent,
} from './part1';
import type {
  CaptchaStreamEvent,
  CatchupSnapshotStreamEvent,
  ContextOverflowResetStreamEvent,
  ContextReferenceWarningStreamEvent,
  CouncilPhaseStreamEvent,
  DagStateUpdateStreamEvent,
  GoalStatusStreamEvent,
  IterationLimitReachedStreamEvent,
  MascotXpUpdateStreamEvent,
  MemoryBriefStreamEvent,
  MessageEndStreamEvent,
  ModelEscalatedStreamEvent,
  ModelFailoverStreamEvent,
  ModelRecoveryStreamEvent,
  PrivacyLevelStreamEvent,
  PrivacyRouteStreamEvent,
  ReasoningStreamEvent,
  RoutingDecisionStreamEvent,
  StatusStreamEvent,
  SubagentCompletionStreamEvent,
  SubagentLogStreamEvent,
  SubagentProgressStreamEvent,
  SubagentStaleStreamEvent,
  SubagentStartStreamEvent,
  TeammateMessageStreamEvent,
  ToolsSnapshotStreamEvent,
  VerificationVerdictStreamEvent,
  WorkingMemoryStreamEvent,
} from './part2';
import type {
  BrowserTakeoverCompletedStreamEvent,
  BrowserTakeoverRequestedStreamEvent,
  BrowserViewUpdateStreamEvent,
  DesktopControlApprovalRequestStreamEvent,
  DesktopEnvelopeProgressStreamEvent,
  DesktopViewUpdateStreamEvent,
  FileDiffStreamEvent,
  FileMutationFailedStreamEvent,
  WorkspaceMergeFailedStreamEvent,
  FissionTopologyUpdateStreamEvent,
  PtcNotifyStreamEvent,
  ToolImageOutputStreamEvent,
} from './part3';

export type AgentStreamEvent =
  | CatchupSnapshotStreamEvent
  | PtcNotifyStreamEvent
  | RateLimitUpdatedStreamEvent
  | RateLimitWarningStreamEvent
  | RateLimitThrottledStreamEvent
  | ErrorStreamEvent
  | AgentCancelledStreamEvent
  | TasksStepsStreamEvent
  | ToolHeartbeatStreamEvent
  | SourcesStreamEvent
  | ToolApprovalRequestStreamEvent
  | ApprovalRequiredStreamEvent
  | AsyncUserMessageStreamEvent
  | ClarificationRequiredStreamEvent
  | RedirectedStreamEvent
  | ArtifactFocusStreamEvent
  | RiskBlockedStreamEvent
  | SessionRecordingStreamEvent
  | CouncilPhaseStreamEvent
  | CapabilityGapStreamEvent
  | SkillGapStreamEvent
  | PhaseTransitionStreamEvent
  | SteeringStreamEvent
  | ToolStartStreamEvent
  | ToolEndStreamEvent
  | ToolFailureStreamEvent
  | ToolStdoutChunkStreamEvent
  | ToolCancelledStreamEvent
  | ToolEvictedRefStreamEvent
  | TokenUsageStreamEvent
  | MessageStreamEvent
  | MemoryBriefStreamEvent
  | ArtifactsStreamEvent
  | ArtifactContentStreamEvent
  | UIUpdateStreamEvent
  | MessageEndStreamEvent
  | ReasoningStreamEvent
  | StatusStreamEvent
  | CaptchaStreamEvent
  | ModelEscalatedStreamEvent
  | ModelFailoverStreamEvent
  | ModelRecoveryStreamEvent
  | ToolsSnapshotStreamEvent
  | RoutingDecisionStreamEvent
  | PrivacyLevelStreamEvent
  | PrivacyRouteStreamEvent
  | SubagentStartStreamEvent
  | SubagentProgressStreamEvent
  | SubagentLogStreamEvent
  | SubagentCompletionStreamEvent
  | SubagentStaleStreamEvent
  | TeammateMessageStreamEvent
  | FileDiffStreamEvent
  | FileMutationFailedStreamEvent
  | WorkspaceMergeFailedStreamEvent
  | ToolImageOutputStreamEvent
  | BrowserViewUpdateStreamEvent
  | DesktopViewUpdateStreamEvent
  | DesktopControlApprovalRequestStreamEvent
  | BrowserTakeoverRequestedStreamEvent
  | BrowserTakeoverCompletedStreamEvent
  | MascotXpUpdateStreamEvent
  | DagStateUpdateStreamEvent
  | IterationLimitReachedStreamEvent
  | ContextOverflowResetStreamEvent
  | ContextReferenceWarningStreamEvent
  | GoalStatusStreamEvent
  | FissionTopologyUpdateStreamEvent
  | VerificationVerdictStreamEvent
  | WorkingMemoryStreamEvent
  | DesktopEnvelopeProgressStreamEvent;
