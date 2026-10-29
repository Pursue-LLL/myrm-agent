/**
 * [INPUT]
 * - (none)
 *
 * [OUTPUT]
 * - APPROVAL_REASON_CODES: 审批卡有文案的理由码，与 harness 引擎的 ApprovalReasonCode 一一对应
 * - ApprovalReasonCode: 理由码类型
 * - parseApprovalReasonCode: 把线上收到的值收窄为已知理由码，未知值视为没有码
 *
 * [POS]
 * 审批理由的稳定标识。卡片按码取 `toolApproval.reasons.*` 文案；没有码或码未知时，卡片直接展示 harness 写下的原文。
 */

export const APPROVAL_REASON_CODES = [
  'path_outside_zones',
  'path_read_only',
  'protected_instruction_write',
  'git_metadata_write',
  'sensitive_file',
  'domain_requires_approval',
  'shell_threat',
] as const;

export type ApprovalReasonCode = (typeof APPROVAL_REASON_CODES)[number];

const KNOWN_CODES: ReadonlySet<string> = new Set(APPROVAL_REASON_CODES);

export function parseApprovalReasonCode(raw: unknown): ApprovalReasonCode | undefined {
  return typeof raw === 'string' && KNOWN_CODES.has(raw) ? (raw as ApprovalReasonCode) : undefined;
}
