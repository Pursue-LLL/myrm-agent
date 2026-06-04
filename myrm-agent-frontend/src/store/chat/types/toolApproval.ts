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

import type { ActionMode } from './sessionConfig';

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
}

/** 工具调用信息（用于 CLI Agent 权限审批和 Diff 预览） */
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
