import type { ToolApprovalRequest } from '@/store/chat/types';
import type { ActionMode } from '@/store/chat/types/sessionConfig';

import {
  parseCommandSpanReasons,
  parseCommandSpanRisks,
  parseCommandSpans,
  parsePlainExplanation,
} from '@/lib/approval/shellCommandDisplay';

interface ApprovalActionPayload {
  action: string;
  args: Record<string, unknown>;
  description: string;
  domains?: string[];
  ptc_annotations?: Record<string, boolean>;
  command_spans?: unknown;
  command_span_risks?: unknown;
  command_span_reasons?: unknown;
  plain_explanation?: unknown;
  execution_intent?: unknown;
  reviewerReason?: string;
}

interface ApprovalExtensionsPayload {
  timeout: {
    seconds: number;
    expiresAt: number;
    behavior?: 'deny' | 'allow';
  };
  displayMode: ToolApprovalRequest['displayMode'];
  workspaceRoot?: string;
}

interface BuildToolApprovalRequestParams {
  action: ApprovalActionPayload;
  reviewConfig?: { domainApproval?: boolean; smartDenied?: boolean; hideAllowAlways?: boolean };
  requestId: string;
  messageId: string;
  chatId: string;
  actionMode: ActionMode;
  extensions: ApprovalExtensionsPayload;
  batchId?: string;
  batchIndex?: number;
  batchSize?: number;
}

function resolvePathGrantMeta(action: ApprovalActionPayload): { eligible: boolean; path?: string; writable: boolean } {
  const reason = action.description || action.reviewerReason || '';
  if (!reason.includes('Path outside allowed zones')) {
    return { eligible: false, writable: false };
  }
  const rawPath =
    (typeof action.args.path === 'string' && action.args.path) ||
    (typeof action.args.file_path === 'string' && action.args.file_path) ||
    (typeof action.args.target_path === 'string' && action.args.target_path) ||
    '';
  if (!rawPath.trim()) {
    return { eligible: true, writable: false };
  }
  const normalized = rawPath.replace(/\\/g, '/');
  const slash = normalized.lastIndexOf('/');
  const grantPath = slash > 0 ? normalized.slice(0, slash) : normalized;
  const writeTools = new Set(['file_write_tool', 'file_edit_tool', 'file_delete_tool']);
  return {
    eligible: true,
    path: grantPath || rawPath.trim(),
    writable: writeTools.has(action.action),
  };
}

export function buildToolApprovalRequest({
  action,
  reviewConfig,
  requestId,
  messageId,
  chatId,
  actionMode,
  extensions,
  batchId,
  batchIndex,
  batchSize,
}: BuildToolApprovalRequestParams): ToolApprovalRequest {
  const shellCommand =
    typeof action.args.command === 'string'
      ? action.args.command
      : typeof action.args.code === 'string'
        ? action.args.code
        : '';

  const commandSpans = parseCommandSpans(action.command_spans, shellCommand.length);
  const pathGrant = resolvePathGrantMeta(action);

  return {
    requestId,
    toolName: action.action,
    toolInput: action.args,
    reason: action.description,
    timeoutSeconds: extensions.timeout.seconds,
    expiresAt: extensions.timeout.expiresAt,
    timeoutBehavior: extensions.timeout.behavior || 'deny',
    messageId,
    displayMode: extensions.displayMode,
    batchId,
    batchIndex,
    batchSize,
    chatId,
    actionMode,
    domains: Array.isArray(action.domains) ? action.domains : undefined,
    domainApproval: reviewConfig?.domainApproval === true ? true : undefined,
    ptcAnnotations: action.ptc_annotations,
    commandSpans,
    commandSpanRisks: commandSpans ? parseCommandSpanRisks(action.command_span_risks, commandSpans.length) : undefined,
    commandSpanReasons: commandSpans
      ? parseCommandSpanReasons(action.command_span_reasons, commandSpans.length)
      : undefined,
    workspaceRoot: extensions.workspaceRoot,
    plainExplanation: parsePlainExplanation(action.plain_explanation),
    executionIntent:
      typeof action.execution_intent === 'string' && action.execution_intent.trim()
        ? action.execution_intent.trim()
        : undefined,
    smartDenied: reviewConfig?.smartDenied === true ? true : undefined,
    hideAllowAlways: reviewConfig?.hideAllowAlways === true ? true : undefined,
    reviewerReason: action.reviewerReason,
    pathGrantEligible: pathGrant.eligible || undefined,
    pathGrantPath: pathGrant.path,
    pathGrantWritable: pathGrant.eligible ? pathGrant.writable : undefined,
  };
}
