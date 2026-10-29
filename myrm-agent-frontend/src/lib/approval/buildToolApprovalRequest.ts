import type { ApprovalGrantDirectory, ToolApprovalRequest } from '@/store/chat/types';
import type { ActionMode } from '@/store/chat/types/sessionConfig';

import { parseApprovalReasonCode } from '@/lib/approval/approvalReasonCode';
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
  reasonCode?: unknown;
  reasonSubject?: unknown;
  domains?: string[];
  ptc_annotations?: Record<string, boolean>;
  command_spans?: unknown;
  command_span_risks?: unknown;
  command_span_reasons?: unknown;
  plain_explanation?: unknown;
  execution_intent?: unknown;
  reviewerReason?: string;
  scriptOperandPath?: string;
  scriptOperandHash?: string;
  grantDirectories?: unknown;
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
  reviewConfig?: {
    domainApproval?: boolean;
    smartDenied?: boolean;
    hideAllowAlways?: boolean;
    scriptOperandProtected?: boolean;
  };
  requestId: string;
  messageId: string;
  chatId: string;
  actionMode: ActionMode;
  extensions: ApprovalExtensionsPayload;
  batchId?: string;
  batchIndex?: number;
  batchSize?: number;
  interruptId?: string;
}

/** The folders the harness planned for "also grant folder access"; malformed entries are dropped. */
function parseGrantDirectories(raw: unknown): ApprovalGrantDirectory[] | undefined {
  if (!Array.isArray(raw)) {
    return undefined;
  }
  const directories: ApprovalGrantDirectory[] = [];
  for (const item of raw) {
    const path = (item as { path?: unknown } | null)?.path;
    if (typeof path === 'string' && path.trim()) {
      directories.push({ path: path.trim(), writable: (item as { writable?: unknown }).writable === true });
    }
  }
  return directories.length > 0 ? directories : undefined;
}

/** The reason's stable code with its subject; neither when the code is absent or one the card has no copy for. */
function parseReasonCode(code: unknown, subject: unknown): Pick<ToolApprovalRequest, 'reasonCode' | 'reasonSubject'> {
  const reasonCode = parseApprovalReasonCode(code);
  if (!reasonCode) {
    return {};
  }
  const reasonSubject = typeof subject === 'string' ? subject.trim() : '';
  return { reasonCode, reasonSubject: reasonSubject || undefined };
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
  interruptId,
}: BuildToolApprovalRequestParams): ToolApprovalRequest {
  const shellCommand =
    typeof action.args.command === 'string'
      ? action.args.command
      : typeof action.args.code === 'string'
        ? action.args.code
        : '';

  const commandSpans = parseCommandSpans(action.command_spans, shellCommand.length);
  const diff =
    typeof action.args.patch === 'string' && action.args.patch.trim()
      ? action.args.patch.trim()
      : typeof action.args.diff === 'string' && action.args.diff.trim()
        ? action.args.diff.trim()
        : undefined;

  return {
    requestId,
    toolName: action.action,
    toolInput: action.args,
    diff,
    reason: action.description,
    ...parseReasonCode(action.reasonCode, action.reasonSubject),
    timeoutSeconds: extensions?.timeout?.seconds ?? 60,
    expiresAt: extensions?.timeout?.expiresAt ?? 0,
    timeoutBehavior: extensions?.timeout?.behavior || 'deny',
    messageId,
    displayMode: extensions?.displayMode,
    batchId,
    batchIndex,
    batchSize,
    interruptId,
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
    grantDirectories: parseGrantDirectories(action.grantDirectories),
    scriptOperandPath:
      typeof action.scriptOperandPath === 'string' && action.scriptOperandPath ? action.scriptOperandPath : undefined,
    scriptOperandHash:
      typeof action.scriptOperandHash === 'string' && action.scriptOperandHash ? action.scriptOperandHash : undefined,
    scriptOperandProtected: reviewConfig?.scriptOperandProtected === true ? true : undefined,
  };
}
