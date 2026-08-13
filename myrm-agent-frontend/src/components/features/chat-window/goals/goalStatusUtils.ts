import type { GoalState } from './goalStatusTypes';

const KNOWN_GOAL_REASON_KEYS: Record<string, string> = {
  'Semantic judge determined goal is complete': 'reasonJudgeComplete',
  'Goal completed via complete_goal_tool': 'reasonToolComplete',
  'Budget exhausted': 'reasonBudgetExhausted',
  'Wait timeout exceeded — goal paused': 'reasonWaitTimeout',
  'Sandbox boundary violation — goal paused for human review': 'reasonSandboxBoundary',
};

export function translateGoalReason(reason: string | undefined, t: (key: string) => string): string | undefined {
  if (!reason) {return undefined;}
  const key = KNOWN_GOAL_REASON_KEYS[reason];
  if (key) {return t(key);}
  if (reason.startsWith('No new progress for ') && reason.includes('convergence reached')) {
    return t('reasonConvergence');
  }
  if (reason.startsWith('Goal drift detected')) {
    return t('reasonDriftDetected');
  }
  if (reason.startsWith('Sandbox boundary violation')) {
    return t('reasonSandboxBoundary');
  }
  if (reason.startsWith('Checkpoint:')) {
    return reason;
  }
  return reason;
}

export function computeEtaSeconds(goal: GoalState, hasSufficientData: boolean, isTerminal: boolean): number | null {
  if (!hasSufficientData || isTerminal || goal.status === 'budget_limited') {return null;}
  const candidates: number[] = [];
  const tokPerSec = goal.tokensUsed / goal.timeUsedSeconds;

  if (goal.budget?.maxTokens && tokPerSec > 0) {
    candidates.push((goal.budget.maxTokens - goal.tokensUsed) / tokPerSec);
  }
  if (goal.budget?.maxTimeSeconds) {
    candidates.push(goal.budget.maxTimeSeconds - goal.timeUsedSeconds);
  }
  if (goal.budget?.maxUsd && goal.costUsd && goal.costUsd > 0) {
    const costPerSec = goal.costUsd / goal.timeUsedSeconds;
    candidates.push((goal.budget.maxUsd - goal.costUsd) / costPerSec);
  }

  const valid = candidates.filter((v) => v > 0);
  return valid.length > 0 ? Math.min(...valid) : null;
}

export function formatEta(seconds: number): string {
  if (seconds < 60) {return '< 1min';}
  if (seconds < 3600) {return `~${Math.round(seconds / 60)}min`;}
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return `~${h}h ${m}m`;
}

export function formatBurnRate(tokPerMin: number): string {
  if (tokPerMin >= 1000) {return `~${(tokPerMin / 1000).toFixed(1)}K/min`;}
  return `~${Math.round(tokPerMin)}/min`;
}

export function getProgressColor(isCritical: boolean, isWarning: boolean): string {
  if (isCritical) {return 'bg-red-500';}
  if (isWarning) {return 'bg-orange-500';}
  return 'bg-primary';
}
