/**
 * [INPUT]: Multi-agent pivot reports, gamified user profile, and team adoption insights.
 * [OUTPUT]: Strong TypeScript definitions for MultiAgentCrossPeriodPivotDeck component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/crossPeriodMilestoneTypes.ts
 */

export type PeriodType = 'weekly' | 'monthly' | 'quarterly' | 'custom';

export interface AgentRuntimeUsagePointItem {
  agent_id: string;
  agent_name: string;
  tokens_in: number;
  tokens_out: number;
  total_tokens: number;
  token_share_pct: number;
  cost_usd: number;
  invocation_count: number;
  success_rate: number;
  avg_latency_ms: number;
}

export interface PeriodAggregateSummaryItem {
  period_type: PeriodType;
  period_label: string;
  start_date: string;
  end_date: string;
  total_tokens: number;
  total_cost_usd: number;
  total_invocations: number;
  agent_breakdowns: AgentRuntimeUsagePointItem[];
}

export interface CrossPeriodPivotReportItem {
  current_period: PeriodAggregateSummaryItem;
  previous_period?: PeriodAggregateSummaryItem | null;
  token_growth_pct?: number | null;
  cost_growth_pct?: number | null;
  invocation_growth_pct?: number | null;
}

export interface DailyEfficiencyTaskItem {
  id: string;
  title: string;
  description: string;
  xp_reward: number;
  is_completed: boolean;
  progress: number;
  max_progress: number;
}

export interface MilestoneBadgeItem {
  id: string;
  name: string;
  description: string;
  tier: 'bronze' | 'silver' | 'gold' | 'platinum';
  icon: string;
  is_unlocked: boolean;
  unlocked_at?: string | null;
}

export interface UserGamifiedProfileItem {
  user_id: string;
  user_name: string;
  level: number;
  rank_title: string;
  current_xp: number;
  next_level_xp: number;
  total_xp: number;
  streak_days: number;
  daily_tasks: DailyEfficiencyTaskItem[];
  badges: MilestoneBadgeItem[];
}

export interface TeamMemberAdoptionLeaderboardItem {
  user_id: string;
  user_name: string;
  department: string;
  streak_days: number;
  sessions_count: number;
  total_tokens: number;
  level: number;
  rank_title: string;
}

export interface TeamAdoptionInsightsItem {
  total_active_members: number;
  average_streak_days: number;
  total_team_sessions: number;
  top_task_categories: Array<{ category: string; count: string }>;
  leaderboard: TeamMemberAdoptionLeaderboardItem[];
}

export interface MultiAgentCrossPeriodPivotDeckProps {
  report: CrossPeriodPivotReportItem;
  profile: UserGamifiedProfileItem;
  teamInsights: TeamAdoptionInsightsItem;
  onPeriodChange?: (period: PeriodType) => void;
  onClaimTask?: (taskId: string) => Promise<void> | void;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}
