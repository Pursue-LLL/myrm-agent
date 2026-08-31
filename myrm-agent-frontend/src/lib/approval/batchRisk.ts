/**
 * [INPUT]
 * - store/useApprovalStore::ApprovalPayload (POS: 全局 Drawer 审批队列契约)
 *
 * [OUTPUT]
 * - BatchItemRiskLevel, BatchRiskItemDetail, BatchRiskReport, classifyBatchApprovalRisk
 *
 * [POS]
 * Client-side mirror of Harness layer batch risk classification contract (zero external deps).
 */

import type { ApprovalPayload } from '@/store/useApprovalStore';

export type BatchItemRiskLevel = 'safe' | 'moderate' | 'high';

export interface BatchRiskItemDetail {
  itemId: string;
  actionType: string;
  toolName: string;
  riskLevel: BatchItemRiskLevel;
  riskReason: string;
}

export interface BatchRiskReport {
  hasHighRisk: boolean;
  totalCount: number;
  highRiskCount: number;
  safeCount: number;
  highRiskItems: BatchRiskItemDetail[];
  safeItemIds: string[];
  allItemIds: string[];
}

const DESTRUCTIVE_COMMAND_PATTERNS: RegExp[] = [
  /\brm\s+-[a-zA-Z]*[rfRF][a-zA-Z]*\b/,
  /\b(mkfs|fdisk|parted|dd\s+if=)\b/,
  /\b(DROP\s+DATABASE|DROP\s+TABLE|TRUNCATE\s+TABLE)\b/i,
  /\b(chmod\s+-R\s+777|chown\s+-R)\b/,
  /\b(shutdown|reboot|init\s+0|halt)\b/,
  /:\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:/,
];

function extractCommandStrings(payload?: Record<string, unknown>): string[] {
  if (!payload) return [];
  const cmds: string[] = [];

  for (const key of ['command', 'cmd', 'script', 'query', 'sql']) {
    const val = payload[key];
    if (typeof val === 'string') cmds.push(val);
  }

  const args = payload.args;
  if (args && typeof args === 'object' && !Array.isArray(args)) {
    for (const key of ['command', 'cmd', 'script', 'query', 'sql']) {
      const val = (args as Record<string, unknown>)[key];
      if (typeof val === 'string') cmds.push(val);
    }
  }

  const toolCalls = payload.tool_calls;
  if (Array.isArray(toolCalls)) {
    for (const tc of toolCalls) {
      if (tc && typeof tc === 'object') {
        const tcArgs = (tc as Record<string, unknown>).args || (tc as Record<string, unknown>).arguments;
        if (tcArgs && typeof tcArgs === 'object' && !Array.isArray(tcArgs)) {
          for (const key of ['command', 'cmd', 'script', 'query', 'sql']) {
            const val = (tcArgs as Record<string, unknown>)[key];
            if (typeof val === 'string') cmds.push(val);
          }
        }
      }
    }
  }

  return cmds;
}

export function classifySingleApprovalRisk(item: ApprovalPayload): { riskLevel: BatchItemRiskLevel; reason: string } {
  // Check smartDenied / hideAllowAlways in reviewConfigs
  const reviewConfigs = item.payload?.reviewConfigs;
  if (Array.isArray(reviewConfigs)) {
    for (const cfg of reviewConfigs) {
      if (cfg && typeof cfg === 'object') {
        if (cfg.smartDenied || cfg.hideAllowAlways) {
          return { riskLevel: 'high', reason: item.reason || 'High-risk review configuration detected' };
        }
      }
    }
  }

  // Check severity
  const sev = (item.severity || '').toLowerCase();
  if (sev === 'critical' || sev === 'high' || sev === 'error') {
    return { riskLevel: 'high', reason: item.reason || `Critical/High severity action (${item.severity})` };
  }

  // Check action_type
  const act = (item.action_type || '').toLowerCase();
  if (['delete_file', 'execute_sql_destructive', 'privilege_escalation', 'system_reboot'].includes(act)) {
    return { riskLevel: 'high', reason: `Destructive action type: ${item.action_type}` };
  }

  // Check tool name
  const toolName = (
    item.payload?.tool_name ||
    item.payload?.tool_calls?.[0]?.name ||
    item.action_type ||
    ''
  ).toLowerCase();
  if (['danger', 'destroy', 'drop_db', 'wipe'].some((k) => toolName.includes(k))) {
    return { riskLevel: 'high', reason: `High-risk tool name: ${toolName}` };
  }

  // Check deep command strings in payload
  const cmdStrings = extractCommandStrings(item.payload as Record<string, unknown>);
  for (const cmd of cmdStrings) {
    for (const pattern of DESTRUCTIVE_COMMAND_PATTERNS) {
      const match = pattern.exec(cmd);
      if (match) {
        return {
          riskLevel: 'high',
          reason: `Destructive command pattern detected in payload: ${match[0]}`,
        };
      }
    }
  }

  return { riskLevel: 'safe', reason: 'Standard safe / approved action' };
}

export function classifyBatchApprovalRisk(items: ApprovalPayload[]): BatchRiskReport {
  const highRiskItems: BatchRiskItemDetail[] = [];
  const safeItemIds: string[] = [];
  const allItemIds: string[] = [];

  for (const item of items) {
    allItemIds.push(item.approval_id);
    const { riskLevel, reason } = classifySingleApprovalRisk(item);
    const toolName = item.payload?.tool_name || item.payload?.tool_calls?.[0]?.name || item.action_type || '';

    if (riskLevel === 'high') {
      highRiskItems.push({
        itemId: item.approval_id,
        actionType: item.action_type,
        toolName,
        riskLevel,
        riskReason: reason,
      });
    } else {
      safeItemIds.push(item.approval_id);
    }
  }

  return {
    hasHighRisk: highRiskItems.length > 0,
    totalCount: items.length,
    highRiskCount: highRiskItems.length,
    safeCount: safeItemIds.length,
    highRiskItems,
    safeItemIds,
    allItemIds,
  };
}
