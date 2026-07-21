/**
 * [INPUT]
 * 多模块 Message 字段依赖（artifacts, tokens, agentStream 等）
 * 
 * [OUTPUT]
 * Message, File, ChatHistoryItem, MentionReference, PaginationInfo, Clarification*.
 * 
 * [POS]
 * 持久化与渲染用的聊天消息实体。
 */

import type { Artifact } from './artifacts';
import type { UIArtifact } from './interactiveUi';
import type { CostStatus, ContextBudget } from './contextMetrics';
import type { MemoryBriefData, MemoryBriefStatus, SensitivityLevel } from './agentStream/part2';
import type { CompletionStatus, ToolCallInfo } from './toolApproval';
import type { CitedMemoryReference, FileMutationFailure, Source } from './sources';
import type { ProgressItem } from './progress';
import type { TokenEconomicsSnapshot, TokenUsage } from './tokens';
import type { ToolImageOutput } from './agentStream/part3';

export interface McpAppView {
  resourceUri: string;
  serverName: string;
  structuredContent?: Record<string, unknown>;
  toolName?: string;
}

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
  wuConsumed?: number; // 本轮 Work Unit 消耗（Sandbox 模式，由 MESSAGE_END 携带）
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
  consensusRefs?: Array<{
    model: string;
    success: boolean;
    elapsed: number;
    content?: string;
  }>;
  modelName?: string; // 最后使用的模型名称
  routingTier?: 'simple' | 'standard' | 'reasoning' | 'complex';
  modelTier?: 'weak' | 'medium';
  privacyLevel?: SensitivityLevel;
  privacyAction?: string;
  privacyRoute?: string;
  completionStatus?: CompletionStatus; // LLM 回复完成状态
  contextBudget?: ContextBudget;
  memoryBudget?: { used: number; total: number }; // 内存注入预算
  citations?: string[]; // 引用的记忆ID
  memoryBrief?: MemoryBriefData; // 发送后、模型首 token 前的记忆简报
  memoryBriefSnapshotId?: string; // 记忆简报快照ID（用于前后追踪）
  memoryBriefStatus?: MemoryBriefStatus; // 记忆简报可用性状态（用于降级可观测）
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
  planConfirmation?: {
    plan: string;
    status: 'waiting' | 'confirmed' | 'edited' | 'skipped';
    planItems?: Array<{ id: string; content: string; status?: string }>;
    totalItems?: number;
    goal?: string;
    source?: 'deep_research' | 'general_agent';
  };
  workflowSuggestion?: {
    status: 'suggested' | 'accepted' | 'dismissed';
  };
  metadata?: Record<string, unknown>; // 消息元数据（如错误信息、配置提示等）
  citedMemoryIds?: string[]; // 本条消息引用的记忆 ID（用于反馈评分）
  citedMemoryRefs?: CitedMemoryReference[]; // 本条消息引用的记忆详情（用于可解释 citation UI）
  fileMutationFailures?: FileMutationFailure[]; // 本轮失败的文件修改操作
  toolImages?: ToolImageOutput[]; // 工具输出的图片（如 computer_use 截屏）
  mcpApps?: McpAppView[]; // MCP Apps (ext-apps) 嵌入式 UI 视图
  sessionRecording?: { filename: string; preview_url: string; content_type: string };
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
  requiresConfirmation?: boolean;
  context?: string | null;
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
  | 'agent'
  | 'git_diff'
  | 'git_staged'
  | 'url'
  | 'codebase'
  | 'wiki_concept'
  | 'wiki_raw_file';

export interface MentionReference {
  type: MentionReferenceType;
  label: string;
  path?: string;
  fileId?: string;
  url?: string;
  source: 'workspace' | 'uploaded' | 'generated' | 'special' | 'wiki';
  size: number | null;
  directory?: string;
  startLine?: number;
  endLine?: number;
  conceptName?: string;
}

export interface PaginationInfo {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}
