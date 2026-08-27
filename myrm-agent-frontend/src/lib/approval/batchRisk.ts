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
  const toolName = (item.payload?.tool_name || item.payload?.tool_calls?.[0]?.name || item.action_type || '').toLowerCase();
  if (['danger', 'destroy', 'drop_db', 'wipe'].some((k) => toolName.includes(k))) {
    return { riskLevel: 'high', reason: `High-risk tool name: ${toolName}` };
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
