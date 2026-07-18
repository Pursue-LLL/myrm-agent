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
  ApprovalProcessedStreamEvent,
  ApprovalRequiredStreamEvent,
  ArtifactContentStreamEvent,
  ArtifactsStreamEvent,
  ClarificationRequiredStreamEvent,
  ErrorStreamEvent,
  MessageStreamEvent,
  RateLimitThrottledStreamEvent,
  RateLimitUpdatedStreamEvent,
  RateLimitWarningStreamEvent,
  SourcesStreamEvent,
  SteeringStreamEvent,
  TasksStepsStreamEvent,
  TokenUsageStreamEvent,
  ToolApprovalRequestStreamEvent,
  ToolCancelledStreamEvent,
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
  SubagentStartStreamEvent,
  SubagentStatusUpdateStreamEvent,
  TeammateMessageStreamEvent,
  ToolFallbackStreamEvent,
  ToolsSnapshotStreamEvent,
} from './part2';
import type {
  BrowserViewUpdateStreamEvent,
  DesktopViewUpdateStreamEvent,
  FileDiffStreamEvent,
  FileMutationFailedStreamEvent,
  FissionTopologyUpdateStreamEvent,
  PtcNotifyStreamEvent,
  ToolImageOutputStreamEvent,
  ToolProgressStreamEvent,
} from './part3';

export type AgentStreamEvent =
  | CatchupSnapshotStreamEvent
  | PtcNotifyStreamEvent
  | ToolProgressStreamEvent
  | RateLimitUpdatedStreamEvent
  | RateLimitWarningStreamEvent
  | RateLimitThrottledStreamEvent
  | ErrorStreamEvent
  | AgentCancelledStreamEvent
  | TasksStepsStreamEvent
  | ToolHeartbeatStreamEvent
  | SourcesStreamEvent
  | ToolApprovalRequestStreamEvent
  | ApprovalProcessedStreamEvent
  | ApprovalRequiredStreamEvent
  | ClarificationRequiredStreamEvent
  | SteeringStreamEvent
  | ToolStartStreamEvent
  | ToolEndStreamEvent
  | ToolFailureStreamEvent
  | ToolStdoutChunkStreamEvent
  | ToolCancelledStreamEvent
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
  | SubagentStatusUpdateStreamEvent
  | TeammateMessageStreamEvent
  | FileDiffStreamEvent
  | FileMutationFailedStreamEvent
  | ToolImageOutputStreamEvent
  | BrowserViewUpdateStreamEvent
  | DesktopViewUpdateStreamEvent
  | MascotXpUpdateStreamEvent
  | DagStateUpdateStreamEvent
  | IterationLimitReachedStreamEvent
  | ContextOverflowResetStreamEvent
  | ToolFallbackStreamEvent
  | ContextReferenceWarningStreamEvent
  | GoalStatusStreamEvent
  | FissionTopologyUpdateStreamEvent;
