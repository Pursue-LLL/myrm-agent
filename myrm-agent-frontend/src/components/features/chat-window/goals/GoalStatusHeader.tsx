'use client';

import type { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { TaskAirbagCapsule } from '@/components/features/checkpoint/TaskAirbagCapsule';
import { activateOnKey } from '@/lib/utils/a11y';
import { PlayIcon, PauseIcon, XCircleIcon, CheckCircleIcon, AlertIcon, GoalIcon } from './goal-icons';
import type { GoalAction, GoalState, GoalStatus } from './goalStatusTypes';
import { formatEta } from './goalStatusUtils';

export function GoalStatusHeader({
  goal,
  gitBranch,
  isTerminal,
  isWarning,
  isCritical,
  etaSeconds,
  hasSufficientData,
  displayReason,
  queueCount,
  onToggleExpand,
  onPause,
  onAction,
  t,
}: {
  goal: GoalState;
  gitBranch: string | null;
  isTerminal: boolean;
  isWarning: boolean;
  isCritical: boolean;
  etaSeconds: number | null;
  hasSufficientData: boolean;
  displayReason: string | undefined;
  queueCount: number;
  onToggleExpand: () => void;
  onPause: () => void;
  onAction: (action: GoalAction, note?: string) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const statusIcon = getStatusIcon(goal);
  const statusText = getStatusText(goal, t);

  return (
    <div
      data-testid="goal-status-header"
      className="p-3 flex items-center justify-between cursor-pointer hover:bg-muted/50"
      onClick={onToggleExpand}
      // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- clickable card with nested action buttons
      role="button"
      tabIndex={0}
      onKeyDown={activateOnKey}
    >
      <div className="flex items-center gap-3 overflow-hidden">
        <div className="flex-shrink-0">{statusIcon}</div>
        <div className="flex flex-col overflow-hidden">
          <span className="text-sm font-medium truncate flex items-center gap-2">
            <GoalIcon className="h-3 w-3 text-muted-foreground" />
            {goal.uiSummary || (goal.objective.length > 120 ? goal.objective.slice(0, 120) + '...' : goal.objective)}
            {gitBranch && <GitBranchBadge branch={gitBranch} />}
          </span>
          <span className="text-xs text-muted-foreground flex items-center gap-2">
            <span
              data-testid="goal-status-badge"
              className={goal.status === 'budget_limited' ? 'text-red-500 font-semibold' : ''}
            >
              {statusText}
            </span>
            {displayReason && (goal.status === 'paused' || goal.status === 'wait') && (
              <>
                <span>•</span>
                <span
                  className={
                    goal.status === 'wait'
                      ? 'text-blue-600 dark:text-blue-400 italic'
                      : 'text-yellow-600 dark:text-yellow-400 italic'
                  }
                >
                  {displayReason}
                </span>
              </>
            )}
            {queueCount > 0 && (
              <>
                <span>•</span>
                <span className="text-muted-foreground/70">
                  +{queueCount} {t('queueTitle').toLowerCase()}
                </span>
              </>
            )}
            {goal.budget?.maxTokens && (
              <>
                <span>•</span>
                <span
                  className={isCritical ? 'text-red-500 font-medium' : isWarning ? 'text-orange-500 font-medium' : ''}
                >
                  {goal.tokensUsed.toLocaleString()} / {goal.budget.maxTokens.toLocaleString()} tokens
                </span>
              </>
            )}
            {goal.budget?.maxTurns && goal.turnsUsed !== undefined && (
              <>
                <span>•</span>
                <span>
                  {goal.turnsUsed}/{goal.budget.maxTurns} turns
                </span>
              </>
            )}
            {goal.costUsd !== undefined && goal.costUsd > 0 && (
              <>
                <span>•</span>
                <span className="text-green-600 font-medium">${goal.costUsd.toFixed(4)}</span>
              </>
            )}
            {etaSeconds !== null && (
              <>
                <span>•</span>
                <span className="text-primary/80 font-medium">{formatEta(etaSeconds)}</span>
              </>
            )}
            {!hasSufficientData && goal.status === 'active' && goal.budget?.maxTokens && (
              <>
                <span>•</span>
                <span className="text-muted-foreground/60 italic">{t('etaCollecting')}</span>
              </>
            )}
          </span>
        </div>
      </div>

      <div
        role="presentation"
        className="flex items-center gap-2"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
        <TaskAirbagCapsule taskId={goal.goalId} refreshKey={`${goal.status}:${goal.turnsUsed ?? 0}`} />
        {!isTerminal && (
          <div className="flex items-center gap-1">
            {goal.status === 'wait' ? (
              <>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  aria-label={t('usageLimitResume')}
                  onClick={() => onAction('unwait')}
                >
                  <PlayIcon className="h-4 w-4" />
                </Button>
                <GoalPauseButton label={t('pauseDialogTitle')} onPause={onPause} />
              </>
            ) : goal.status === 'active' ? (
              <GoalPauseButton label={t('pauseDialogTitle')} onPause={onPause} />
            ) : (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                aria-label={t('usageLimitResume')}
                onClick={() => onAction('resume')}
              >
                <PlayIcon className="h-4 w-4" />
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-destructive hover:text-destructive"
              aria-label={t('cancel')}
              onClick={() => onAction('cancel')}
            >
              <XCircleIcon className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

function GoalPauseButton({ label, onPause }: { label: string; onPause: () => void }) {
  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-8 w-8"
      aria-label={label}
      data-testid="goal-pause-trigger"
      onClick={onPause}
    >
      <PauseIcon className="h-4 w-4" />
    </Button>
  );
}

function GitBranchBadge({ branch }: { branch: string }) {
  return (
    <span className="ml-1 inline-flex items-center rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground border">
      <svg
        className="w-3 h-3 mr-1"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <line x1="6" y1="3" x2="6" y2="15" />
        <circle cx="18" cy="6" r="3" />
        <circle cx="6" cy="18" r="3" />
        <path d="M18 9a9 9 0 0 1-9 9" />
      </svg>
      {branch}
    </span>
  );
}

function getStatusIcon(goal: { status: GoalStatus; verdict?: string; reason?: string }) {
  switch (goal.status) {
    case 'active':
      return <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />;
    case 'paused':
      if (goal.verdict === 'drift_pause') {
        const isSandbox = goal.reason?.startsWith('Sandbox boundary');
        return <AlertIcon className={`h-4 w-4 ${isSandbox ? 'text-red-500' : 'text-orange-500'} animate-pulse`} />;
      }
      return <PauseIcon className="h-4 w-4 text-yellow-500" />;
    case 'wait':
      return <PauseIcon className="h-4 w-4 text-blue-500 animate-pulse" />;
    case 'needs_human_review':
      return <AlertIcon className="h-4 w-4 text-red-500 animate-pulse" />;
    case 'budget_limited':
      return <AlertIcon className="h-4 w-4 text-orange-500" />;
    case 'complete':
      return <CheckCircleIcon className="h-4 w-4 text-green-500" />;
    case 'cancelled':
      return <XCircleIcon className="h-4 w-4 text-red-500" />;
  }
}

function getStatusText(
  goal: { status: GoalStatus; verdict?: string; reason?: string; loopRestarts?: number },
  t: (key: string) => string,
) {
  switch (goal.status) {
    case 'active':
      if (goal.verdict === 'loop_restart') {
        return `${t('statusLoopRestart')} (#${goal.loopRestarts ?? 0})`;
      }
      return t('statusActive');
    case 'paused':
      if (goal.verdict === 'drift_pause') {
        return goal.reason?.startsWith('Sandbox boundary') ? t('statusSandboxPaused') : t('statusDriftPaused');
      }
      return t('statusPaused');
    case 'wait':
      return t('statusWait');
    case 'needs_human_review':
      return t('statusNeedsHumanReview') || 'Needs Human Review';
    case 'budget_limited':
      return t('statusBudgetLimited');
    case 'complete':
      return goal.verdict === 'convergence' ? t('statusConverged') : t('statusComplete');
    case 'cancelled':
      return t('statusCancelled');
  }
}
