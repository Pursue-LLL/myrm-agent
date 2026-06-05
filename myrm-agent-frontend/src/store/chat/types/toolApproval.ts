/**
 * [INPUT]
 * ./sessionConfig::ActionMode (POS: 会话级 Agent 与模式配置类型)
 * 
 * [OUTPUT]
 * ToolApprovalRequest, ToolCallInfo, CompletionStatus.
 * 
 * [POS]
 * 工具审批与 CLI diff 预览契约。
 */

import type { ActionMode } from './sessionConfig';

export type { CommandSpan } from '@/lib/approval/shellCommandDisplay';

/** 工具审批请求（Permission Engine 触发） */
export interface ToolApprovalRequest {
  requestId: string;
  toolName: string;
  toolInput: Record<string, unknown>;
  reason: string;
  timeoutSeconds: number;
  expiresAt: number;
  /** Action to take when timeout expires: "deny" (default) or "allow" */
  timeoutBehavior: 'deny' | 'allow';
  messageId: string;
  displayMode: 'approval' | 'handover';
  chatId: string;
  actionMode: ActionMode;
  batchId?: string;
  batchIndex?: number;
  batchSize?: number;
  /** URL-bearing tools: hostnames extracted from tool arguments */
  domains?: string[];
  /** Whether Domain HITL is active for this request */
  domainApproval?: boolean;
  /** PTC/MCP annotations (e.g. readOnlyHint, destructiveHint) */
  ptcAnnotations?: Record<string, boolean>;
  /** Pipeline segment highlight spans (shell approval UX) */
  commandSpans?: { startIndex: number; endIndex: number }[];
  /** Per-segment risk from harness risk_classifier */
  commandSpanRisks?: ('safe' | 'unknown')[];
  /** Sandbox workspace root for shell approvals */
  workspaceRoot?: string;
}
export interface ToolCallInfo {
  callId: string;
  toolName: string;
  arguments: Record<string, unknown>;
  requiresApproval: boolean;
  status: 'pending' | 'approved' | 'rejected' | 'completed';
  /** Diff 内容（apply_patch/edit_file 工具调用） */
  diff?: string;
  /** 文件路径 */
  filePath?: string;
  /** PTC/MCP annotations (e.g. readOnlyHint, destructiveHint) */
  ptcAnnotations?: Record<string, boolean>;
}
export type CompletionStatus = 'complete' | 'truncated' | 'filtered' | 'budget_blocked';
