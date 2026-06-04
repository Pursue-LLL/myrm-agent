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
  CaptchaStreamEvent,
  ClarificationRequiredStreamEvent,
  ClientActionStreamEvent,
  ErrorStreamEvent,
  MessageEndStreamEvent,
  MessageStreamEvent,
  ModelEscalatedStreamEvent,
  ModelFailoverStreamEvent,
  ModelRecoveryStreamEvent,
  RateLimitThrottledStreamEvent,
  RateLimitUpdatedStreamEvent,
  RateLimitWarningStreamEvent,
  ReasoningStreamEvent,
  RoutingDecisionStreamEvent,
  SourcesStreamEvent,
  StatusStreamEvent,
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
  BrowserViewUpdateStreamEvent,
  CatchupSnapshotStreamEvent,
  GoalStatusStreamEvent,
  ContextOverflowResetStreamEvent,
  ContextReferenceWarningStreamEvent,
  DagStateUpdateStreamEvent,
  DesktopViewUpdateStreamEvent,
  FileDiffStreamEvent,
  FileMutationFailedStreamEvent,
  FissionTopologyUpdateStreamEvent,
  IterationLimitReachedStreamEvent,
  MascotXpUpdateStreamEvent,
  PrivacyLevelStreamEvent,
  PrivacyRouteStreamEvent,
  PtcNotifyStreamEvent,
  SubagentCompletionStreamEvent,
  SubagentLogStreamEvent,
  SubagentProgressStreamEvent,
  SubagentStartStreamEvent,
  SubagentStatusUpdateStreamEvent,
  TeammateMessageStreamEvent,
  ToolFallbackStreamEvent,
  ToolImageOutputStreamEvent,
  ToolProgressStreamEvent,
  ToolsSnapshotStreamEvent,
} from './part2';

export type AgentStreamEvent =
  | ClientActionStreamEvent
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
