/**
 * Tiered Risk HITL Approval & Dry-Run Preview Types.
 *
 * [INPUT] None
 * [OUTPUT] RiskTier, TieredRiskEvaluation, RiskConfirmPayload, DryRunSimulationResult
 * [POS] Type contracts for Item 29 TieredRiskHitlConfirmationModalAndDryRunPreviewGate.
 * Zero `any`.
 */

export type RiskTier = 'READ' | 'WRITE' | 'HIGH_RISK';

export interface TieredRiskEvaluation {
  tier: RiskTier;
  tool_name: string;
  target_entity: string | null;
  risk_reasons: string[];
  supports_dry_run: boolean;
  is_dry_run: boolean;
  need_confirmation: boolean;
  confirmation_token: string | null;
  suggested_action: string;
  param_summary: Record<string, string>;
}

export interface RiskConfirmPayload {
  confirmation_token: string;
  approved: boolean;
  modified_input?: Record<string, unknown> | null;
  reason?: string | null;
}

export interface DryRunSimulationResult {
  simulated: boolean;
  tool_name: string;
  simulated_impact: string;
  affected_target: string | null;
  predicted_changes: string[];
}

export interface RiskConfirmationCardProps {
  evaluation: TieredRiskEvaluation;
  onConfirm: (payload: RiskConfirmPayload) => Promise<void> | void;
  onReject: (reason?: string) => Promise<void> | void;
  onSimulateDryRun?: (toolName: string, params: Record<string, unknown>) => Promise<DryRunSimulationResult | null>;
  className?: string;
}
