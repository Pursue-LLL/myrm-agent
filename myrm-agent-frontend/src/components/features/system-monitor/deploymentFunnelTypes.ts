/**
 * [INPUT]: Deployment IDs, stage metrics, feedback sentiment records, and autonomous goal proposals.
 * [OUTPUT]: Strong TypeScript definitions for deployment funnel dropoff analytics and feedback nudge loop dashboard.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/deploymentFunnelTypes.ts
 */

export type FunnelStage =
  | 'STAGE_1_VIEW'
  | 'STAGE_2_ENGAGE'
  | 'STAGE_3_ACTION'
  | 'STAGE_4_COMPLETE';

export type FeedbackSentiment = 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE';

export interface StageDropoffMetric {
  stage: FunnelStage;
  user_count: number;
  conversion_rate_pct: number;
  dropoff_rate_pct: number;
}

export interface DeploymentFunnelSnapshot {
  deployment_id: string;
  total_visitors: number;
  stages: StageDropoffMetric[];
  dropoff_hotspot_stage: FunnelStage | null;
  feedback_counts: Record<FeedbackSentiment, number>;
  nudge_required: boolean;
  nudge_reason: string | null;
  autonomous_goal_recommendation: string | null;
  evaluated_at: string;
}

export interface DeploymentFunnelDashboardProps {
  snapshot: DeploymentFunnelSnapshot;
  onRefresh?: () => void;
  onDispatchAutonomousGoal?: (goal: string) => Promise<void> | void;
  isDispatching?: boolean;
}
