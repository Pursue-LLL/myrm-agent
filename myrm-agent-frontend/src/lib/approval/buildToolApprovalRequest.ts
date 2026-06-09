import type { ToolApprovalRequest } from '@/store/chat/types';
import type { ActionMode } from '@/store/chat/types/sessionConfig';

import {
  parseCommandSpanReasons,
  parseCommandSpanRisks,
  parseCommandSpans,
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
  reviewConfig?: { domainApproval?: boolean };
  requestId: string;
  messageId: string;
  chatId: string;
  actionMode: ActionMode;
  extensions: ApprovalExtensionsPayload;
  batchId?: string;
  batchIndex?: number;
  batchSize?: number;
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
    commandSpanRisks: commandSpans
      ? parseCommandSpanRisks(action.command_span_risks, commandSpans.length)
      : undefined,
    commandSpanReasons: commandSpans
      ? parseCommandSpanReasons(action.command_span_reasons, commandSpans.length)
      : undefined,
    workspaceRoot: extensions.workspaceRoot,
  };
}
