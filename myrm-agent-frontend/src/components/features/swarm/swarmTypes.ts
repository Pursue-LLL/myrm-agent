/**
 * [INPUT]
 * - None (pure TypeScript type definitions)
 *
 * [OUTPUT]
 * - SwarmModeConfig, SwarmSubagentTask, RecalledRuleItem, OwnerRiskItem, RiskSeverityLevel
 *
 * [POS]
 * Type definitions for Swarm Coordination, Memory Recall HUD & Owner Risk Checklist (Item 42 P0).
 * Strictly under 100 lines. Zero `any`.
 */

export type RiskSeverityLevel = "low" | "medium" | "high" | "critical";

export interface SwarmModeConfig {
  enabled: boolean;
  concurrencyQuota: number;
  autoDecompose: boolean;
  sessionId: string;
}

export interface SwarmSubagentTask {
  taskId: string;
  roleTitle: string;
  boundaryDescription: string;
  status: "pending" | "running" | "completed" | "failed";
  currentStep?: string;
  assignedTools?: string[];
}

export interface RecalledRuleItem {
  ruleId: string;
  summary: string;
  sourceTurnId: string;
  confidence: number;
  isActive: boolean;
  category: string;
  createdAtMs?: number;
}

export interface OwnerRiskItem {
  riskId: string;
  title: string;
  description: string;
  severity: RiskSeverityLevel;
  isConfirmed: boolean;
  confirmedBy?: string;
  externalConstraintType: string;
  remediationHint?: string;
}
