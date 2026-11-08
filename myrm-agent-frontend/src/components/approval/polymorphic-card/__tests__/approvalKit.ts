/** Builders shared by the polymorphic-card suites. */
import type { ApprovalPayload, ApprovalPayloadData, ApprovalToolCall } from '@/store/useApprovalStore';
import type { ApprovalFlags } from '../approvalFlags';

/** The exact pattern the theme gate rejects: the fill token used as a text colour. */
export const BARE_DESTRUCTIVE_TEXT = /(?<![\w-])text-destructive(?![\w-])/;

export const makeApproval = (
  action_type: string,
  payload?: ApprovalPayloadData,
  extra: Partial<ApprovalPayload> = {},
): ApprovalPayload => ({
  approval_id: 'appr-1',
  user_id: 'user-1',
  status: 'PENDING',
  severity: 'warning',
  action_type,
  payload,
  ...extra,
});

export const shellCall = (args: Record<string, unknown> = { command: 'ls -la' }): ApprovalToolCall => ({
  name: 'bash_code_execute_tool',
  args,
});

export const subagentApproval = (
  toolCalls: ApprovalToolCall[],
  extra: Partial<ApprovalPayload> = {},
): ApprovalPayload => makeApproval('subagent_approval', { tool_calls: toolCalls }, extra);

/** Flags of an approval nothing is wrong with. */
export const noFlags: ApprovalFlags = {
  hasAnySmartDenied: false,
  autoModeSuspendedBreach: undefined,
  isSociallyIrreversible: false,
  isIrreversibleDestructive: false,
  destructiveBlastRadius: undefined,
  destructiveSnapshotId: undefined,
  hasAnyHideAllowAlways: false,
  spendConfig: null,
};
