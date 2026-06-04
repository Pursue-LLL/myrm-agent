/**
 * [INPUT]
 * @/store/config/providerTypes::SingleModelSelection (POS: Provider/model selection type contract)
 *
 * [OUTPUT]
 * Chat message, stream event, artifact, memory citation and store state TypeScript contracts.
 *
 * [POS]
 * Chat state and SSE event type definitions. Split from monolithic types.ts for maintainability.
 */

import type { Artifact } from './artifacts';
import type { UIArtifact } from './interactiveUi';
import type { CostStatus, ContextBudget } from './contextMetrics';
import type { SensitivityLevel } from './agentStream/part2';
import type { CompletionStatus, ToolCallInfo } from './toolApproval';
import type { CitedMemoryReference, FileMutationFailure, Source } from './sources';
import type { ProgressItem } from './progress';
import type { TokenEconomicsSnapshot, TokenUsage } from './tokens';
import type { ToolImageOutput } from './agentStream/part3';

export type Message = {
  messageId: string;
  chatId: string;
  createdAt: Date;
  content: string;
  reasoning?: string;
  reasoningStartedAt?: number;
  reasoningDurationMs?: number;
  role: 'user' | 'assistant' | 'system';
  isCompactedSummaryView?: boolean;
  suggestions?: string[];
  sources?: Source[]; // 外部引用来源
  progressSteps?: ProgressItem[];
  searchItems?: string[];
  readingItems?: string[];
  thinkingItems?: string[];
  usage?: TokenUsage; // Token 使用量统计（最终累计）
  tokenEconomics?: TokenEconomicsSnapshot; // 细粒度成本与 Token 模型归因
  costUsd?: number; // LLM 调用总成本（USD）
  costStatus?: CostStatus; // 成本计算来源 (actual/estimated/unknown)
  cacheBreakReason?: string; // Prompt cache break 归因原因
  cacheSuggestedActions?: string; // Cache break 行动建议
  mediaAnalysisStatus?: 'analyzing_image' | 'analyzing_video' | null; // 媒体分析中的实时状态（图片/视频）
  consensusMeta?: {
    models_used: number;
    models_succeeded: number;
    aggregator_model: string;
    elapsed_seconds: number;
  };
  modelName?: string; // 最后使用的模型名称
  routingTier?: 'simple' | 'standard' | 'reasoning' | 'complex';
  privacyLevel?: SensitivityLevel;
  privacyAction?: string;
  privacyRoute?: string;
  completionStatus?: CompletionStatus; // LLM 回复完成状态
  contextBudget?: ContextBudget;
  memoryBudget?: { used: number; total: number }; // 内存注入预算
  citations?: string[]; // 引用的记忆ID
  artifacts?: Artifact[]; // 生成的工件
  uiArtifacts?: UIArtifact[]; // 交互式 UI 工件
  isFadingOut?: boolean; // 标记内容正在淡出（工具调用时清空中间内容）
  toolCalls?: ToolCallInfo[];
  files?: File[];
  sendFailed?: boolean;
  clarification?: {
    question?: string;
    answered: boolean;
    options?: string[];
    allowMultiple?: boolean;
    title?: string;
    form?: ClarificationForm;
    isResumeMode?: boolean;
  };
  metadata?: Record<string, unknown>; // 消息元数据（如错误信息、配置提示等）
  citedMemoryIds?: string[]; // 本条消息引用的记忆 ID（用于反馈评分）
  citedMemoryRefs?: CitedMemoryReference[]; // 本条消息引用的记忆详情（用于可解释 citation UI）
  fileMutationFailures?: FileMutationFailure[]; // 本轮失败的文件修改操作
  toolImages?: ToolImageOutput[]; // 工具输出的图片（如 computer_use 截屏）
  siblingGroupId?: string;
  siblingCount?: number;
  siblingIndex?: number;
};

export interface File {
  id?: string; // 文件 ID（StorageProvider 分配）
  fileName: string;
  fileExtension: string;
  fileUrl?: string; // Sandbox 模式：服务器 URL
  localPath?: string; // Tauri 模式：本地绝对路径
  fileType: 'uploaded' | 'local_path';
  contentHash?: string; // SHA-256 内容哈希，用于同会话去重
}

export interface ClarificationOption {
  id: string;
  label: string;
  description?: string;
}

export interface ClarificationQuestion {
  id: string;
  prompt: string;
  options?: ClarificationOption[];
  allowMultiple?: boolean;
}

export interface ClarificationForm {
  title?: string | null;
  questions: ClarificationQuestion[];
}

export interface ChatHistoryItem {
  id: string;
  title: string;
  firstMessage: string;
  lastMessage: string;
  actionMode: string;
  source: string;
  isCompacted?: boolean;
  isPinned?: boolean;
  pinOrder?: number;
  projectId?: string | null;
  updatedAt: Date;
  createdAt: Date;
}

export type MentionReferenceType =
  | 'workspace_file'
  | 'workspace_folder'
  | 'uploaded_file'
  | 'generated_file'
  | 'git_diff'
  | 'git_staged'
  | 'url';

export interface MentionReference {
  type: MentionReferenceType;
  label: string;
  path?: string;
  fileId?: string;
  url?: string;
  source: 'workspace' | 'uploaded' | 'generated' | 'special';
  size: number | null;
  directory?: string;
  startLine?: number;
  endLine?: number;
}

export interface ArchiveRestoreAction {
  type: 'archive_restore';
  restoreArg: string;
}

export interface ArchiveRestoreRangeHint {
  range_arg: string;
  reason?: string;
  start_line?: number;
  end_line?: number;
  label?: string;
}

export interface ArchiveRestoreContentFeature {
  feature_type: string;
  count: number;
  values: string[];
}

export interface ArchiveRestoreBlockPayload {
  type?: 'archive_restore_blocked';
  reason?: string;
  message?: string;
  suggested_action?: string;
  archive_path?: string;
  estimated_tokens?: number;
  reason_label_key?: string;
  severity?: 'info' | 'warning' | 'critical';
  primary_restore_arg?: string;
  recommended_ranges?: string[];
  restore_range_hints?: ArchiveRestoreRangeHint[];
  content_features?: ArchiveRestoreContentFeature[];
  guidance_source?: string;
  fallback_reason?: string;
}

export interface ArchiveRestoreResultPayload {
  type?: 'archive_restore_result';
  outcome?: 'restored';
  archive_path: string;
  restore_arg: string;
  start_line: number;
  end_line: number;
  restored_line_count: number;
  estimated_tokens: number;
  restored_bytes: number;
}

export interface PaginationInfo {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}
