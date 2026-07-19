import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Progress } from '@/components/primitives/progress';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import useChatStore from '@/store/useChatStore';
import { fetchWithTimeout } from '@/lib/api';
import { toast } from 'sonner';
import { notificationService } from '@/services/notification';
import { PlayIcon, PauseIcon, XCircleIcon, CheckCircleIcon, AlertIcon, GoalIcon, BellIcon } from './goal-icons';

const KNOWN_GOAL_REASON_KEYS: Record<string, string> = {
  'Semantic judge determined goal is complete': 'reasonJudgeComplete',
  'Goal completed via complete_goal_tool': 'reasonToolComplete',
  'Budget exhausted': 'reasonBudgetExhausted',
  'Wait timeout exceeded — goal paused': 'reasonWaitTimeout',
};

function translateGoalReason(reason: string | undefined, t: (key: string) => string): string | undefined {
  if (!reason) return undefined;
  const key = KNOWN_GOAL_REASON_KEYS[reason];
  if (key) return t(key);
  if (reason.startsWith('No new progress for ') && reason.includes('convergence reached')) {
    return t('reasonConvergence');
  }
  return reason;
}

export type GoalStatus =
  | 'queued'
  | 'active'
  | 'pending_approval'
  | 'paused'
  | 'wait'
  | 'budget_limited'
  | 'complete'
  | 'cancelled'
  | 'needs_human_review';

export interface AcceptanceResultItem {
  label: string;
  passed: boolean;
  duration_ms: number;
  reason?: string;
  error_logs?: string;
}

export interface AcceptanceHistoryEntry {
  timestamp: string;
  results: AcceptanceResultItem[];
}

export interface GoalState {
  goalId: string;
  objective: string;
  uiSummary?: string;
  status: GoalStatus;
  tokensUsed: number;
  timeUsedSeconds: number;
  costUsd?: number;
  turnsUsed?: number;
  budget?: {
    maxTokens?: number;
    maxUsd?: number;
    maxTimeSeconds?: number;
    maxTurns?: number;
    convergenceWindow?: number;
    loopOnPause?: boolean;
    maxLoopRestarts?: number;
  };
  noProgressStreak?: number;
  loopRestarts?: number;
  verdict?: string;
  reason?: string;
  constraints?: string[];
  acceptanceCriteria?: { type: string; command?: string; criteria?: string }[];
  acceptanceResults?: AcceptanceResultItem[];
  acceptanceHistory?: AcceptanceHistoryEntry[];
  subgoals?: { text: string }[];
  executionSummary?: {
    files_modified: string[];
    verifications: { cmd: string; passed: boolean }[];
    browser_checks: number;
    total_tokens: number;
    total_cost_usd: number;
    execution_duration_s: number;
    turns_used: number;
  };
}

function AcceptanceCriteriaPanel({
  criteria,
  results,
  history,
  t,
}: {
  criteria: { type: string; command?: string; criteria?: string }[];
  results?: AcceptanceResultItem[];
  history?: AcceptanceHistoryEntry[];
  t: ReturnType<typeof useTranslations>;
}) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const passedCount = results?.filter((r) => r.passed).length ?? 0;
  const totalCount = results?.length ?? criteria.length;
  const hasResults = results && results.length > 0;

  return (
    <div className="mt-3 border-t border-border/50 pt-3">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-primary/80">{t('acceptanceCriteria')}</span>
        {hasResults && (
          <span
            className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
              passedCount === totalCount
                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                : 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
            }`}
          >
            {passedCount}/{totalCount}
          </span>
        )}
      </div>

      <ul className="space-y-1">
        {criteria.map((ac, idx) => {
          const result = results?.[idx];
          const isExpanded = expandedIdx === idx;

          return (
            <li key={idx} className="text-xs">
              <div
                className={`flex items-start gap-2 p-1.5 rounded-lg border cursor-pointer transition-colors ${
                  result
                    ? result.passed
                      ? 'bg-green-50/50 border-green-200/50 dark:bg-green-900/10 dark:border-green-800/30'
                      : 'bg-red-50/50 border-red-200/50 dark:bg-red-900/10 dark:border-red-800/30'
                    : 'bg-primary/5 border-primary/10'
                }`}
                onClick={() => setExpandedIdx(isExpanded ? null : idx)}
              >
                <span className="flex-shrink-0 mt-0.5">
                  {result ? (
                    result.passed ? (
                      <CheckCircleIcon className="h-3.5 w-3.5 text-green-600 dark:text-green-400" />
                    ) : (
                      <XCircleIcon className="h-3.5 w-3.5 text-red-600 dark:text-red-400" />
                    )
                  ) : (
                    <span className="text-primary/60 font-mono text-[10px]">
                      {ac.type === 'shell' ? '$' : '>'}
                    </span>
                  )}
                </span>
                <span className="text-foreground/80 break-words leading-relaxed flex-1">
                  {ac.type === 'shell' ? ac.command : ac.criteria}
                </span>
                {result && (
                  <span className="flex-shrink-0 text-[10px] text-muted-foreground tabular-nums">
                    {result.duration_ms}ms
                  </span>
                )}
              </div>
              {isExpanded && result && !result.passed && result.error_logs && (
                <pre className="mt-1 ml-6 p-2 text-[10px] bg-muted/60 rounded border border-border/50 overflow-x-auto max-h-32 whitespace-pre-wrap text-muted-foreground">
                  {result.error_logs}
                </pre>
              )}
              {isExpanded && result && result.reason && (
                <p className="mt-1 ml-6 text-[10px] text-muted-foreground italic">
                  {result.reason}
                </p>
              )}
            </li>
          );
        })}
      </ul>

      {/* History Toggle */}
      {history && history.length > 1 && (
        <div className="mt-2">
          <button
            className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => setShowHistory(!showHistory)}
          >
            {showHistory ? t('hideHistory') : t('showHistory', { count: history.length })}
          </button>
          {showHistory && (
            <div className="mt-1.5 space-y-1.5 max-h-40 overflow-y-auto">
              {history.slice(0, -1).reverse().map((entry, hIdx) => {
                const hPassed = entry.results.filter((r) => r.passed).length;
                const hTotal = entry.results.length;
                return (
                  <div
                    key={hIdx}
                    className="flex items-center gap-2 text-[10px] text-muted-foreground/70 pl-2 border-l-2 border-border/30"
                  >
                    <span className="tabular-nums">
                      {new Date(entry.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <span className={hPassed === hTotal ? 'text-green-600' : 'text-orange-600'}>
                      {hPassed}/{hTotal}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function GoalStatusCard() {
  const t = useTranslations('Goal');
  const [isExpanded, setIsExpanded] = useState(false);
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission>('default');
  const [isEditingObjective, setIsEditingObjective] = useState(false);
  const [editedObjective, setEditedObjective] = useState('');
  const [isSavingObjective, setIsSavingObjective] = useState(false);
  const [pauseDialogOpen, setPauseDialogOpen] = useState(false);
  const [pauseNote, setPauseNote] = useState('');
  const [isPausing, setIsPausing] = useState(false);
  const goal = useGoalStore((state) => state.activeGoal);
  const gitBranch = useGoalStore((state) => state.gitBranch);
  const queueCount = useGoalStore((state) => state.queuedGoals.length);
  const chatId = useChatStore((state) => state.chatId);

  useEffect(() => {
    setNotificationPermission(notificationService.permission);
    if (chatId) {
      useGoalStore.getState().fetchQueue(chatId);
      fetchWithTimeout(`/goals/${chatId}/status`)
        .then((res) => (res.ok ? res.json() : null))
        .then(async (data) => {
          if (data?.goal) {
            const { normalizeGoalState } = await import('@/store/chat/messageStream/streamHelpers');
            useGoalStore.getState().setActiveGoal(normalizeGoalState(data.goal));
          }
        })
        .catch(() => {});
    }
  }, [chatId]);

  useEffect(() => {
    const handleBranchSwitched = (e: CustomEvent) => {
      const data = e.detail;
      if (data.chat_id === chatId) {
        useGoalStore.getState().setGitBranch(data.branch);
        if (data.branch) {
          toast(
            data.restored
              ? t('branchSwitchedRestored', { branch: data.branch })
              : t('branchSwitchedStashed', { branch: data.branch }),
          );
        }
      }
    };
    window.addEventListener('goal:branch_switched', handleBranchSwitched as EventListener);
    return () => {
      window.removeEventListener('goal:branch_switched', handleBranchSwitched as EventListener);
    };
  }, [chatId, t]);

  const handleRequestNotification = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const permission = await notificationService.requestPermission();
    setNotificationPermission(permission);
    if (permission === 'granted') {
      toast.success(t('notificationEnabled'));
    } else {
      toast.error(t('notificationDenied'));
    }
  };

  if (!goal || !chatId) return null;

  const canEditObjective = !['complete', 'cancelled'].includes(goal.status);

  const handleStartEditObjective = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditedObjective(goal.objective);
    setIsEditingObjective(true);
  };

  const handleCancelEditObjective = () => {
    setIsEditingObjective(false);
    setEditedObjective('');
  };

  const handleSaveObjective = async () => {
    const trimmed = editedObjective.trim();
    if (!trimmed || trimmed === goal.objective) {
      handleCancelEditObjective();
      return;
    }
    setIsSavingObjective(true);
    try {
      await useGoalStore.getState().updateObjective(chatId, trimmed);
      toast.success(t('objectiveUpdated'));
      setIsEditingObjective(false);
    } catch (err) {
      toast.error(t('objectiveUpdateFailed'));
      console.error('Failed to update objective:', err);
    } finally {
      setIsSavingObjective(false);
    }
  };

  const handleAction = async (
    action: 'pause' | 'resume' | 'cancel' | 'approve' | 'reject' | 'unwait',
    note?: string,
  ) => {
    try {
      const payload: { action: string; note?: string } = { action };
      if (note?.trim()) {
        payload.note = note.trim();
      }
      const res = await fetchWithTimeout(`/goals/${chatId}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        toast.error(t(`goalActionFailed_${action}` as 'goalActionFailed_pause'));
        return;
      }
      toast.success(t(`goalActionSuccess_${action}` as 'goalActionSuccess_pause'));
      // Optimistic update
      let newStatus: GoalStatus = goal.status;
      if (action === 'pause') newStatus = 'paused';
      else if (action === 'resume' || action === 'reject' || action === 'unwait') newStatus = 'active';
      else if (action === 'cancel') newStatus = 'cancelled';
      else if (action === 'approve') newStatus = 'complete';

      useGoalStore.getState().updateGoalStatus(newStatus, note?.trim() || undefined);
    } catch (e) {
      console.error(`Network error: failed to ${action} goal`, e);
      toast.error(t(`goalActionFailed_${action}` as 'goalActionFailed_pause'));
    }
  };

  const handleConfirmPause = async () => {
    setIsPausing(true);
    try {
      await handleAction('pause', pauseNote);
      setPauseDialogOpen(false);
      setPauseNote('');
    } finally {
      setIsPausing(false);
    }
  };

  const handleAddSubgoal = async (text: string) => {
    if (!text.trim()) return;
    try {
      const res = await fetchWithTimeout(`/goals/${chatId}/subgoals`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) {
        toast.error('Failed to add subgoal');
        return;
      }
      toast.success(t('subgoalAdded') || 'Subgoal added');
    } catch (e) {
      console.error('Failed to add subgoal', e);
      toast.error('Network error: failed to add subgoal');
    }
  };

  const handleRemoveSubgoal = async (index: number) => {
    try {
      const res = await fetchWithTimeout(`/goals/${chatId}/subgoals/${index}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        toast.error('Failed to remove subgoal');
        return;
      }
      toast.success(t('subgoalRemoved') || 'Subgoal removed');
    } catch (e) {
      console.error('Failed to remove subgoal', e);
      toast.error('Network error: failed to remove subgoal');
    }
  };

  const getStatusIcon = () => {
    switch (goal.status) {
      case 'active':
        return <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />;
      case 'paused':
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
  };

  const getStatusText = () => {
    switch (goal.status) {
      case 'active':
        if (goal.verdict === 'loop_restart') {
          const restartNum = goal.loopRestarts ?? 0;
          return `${t('statusLoopRestart')} (#${restartNum})`;
        }
        return t('statusActive');
      case 'paused':
        return t('statusPaused');
      case 'wait':
        return t('statusWait');
      case 'needs_human_review':
        return t('statusNeedsHumanReview') || 'Needs Human Review';
      case 'budget_limited':
        return t('statusBudgetLimited');
      case 'complete':
        if (goal.verdict === 'convergence') return t('statusConverged');
        return t('statusComplete');
      case 'cancelled':
        return t('statusCancelled');
    }
  };

  const tokenProgress = goal.budget?.maxTokens ? (goal.tokensUsed / goal.budget.maxTokens) * 100 : 0;
  const isTerminal = goal.status === 'complete' || goal.status === 'cancelled';

  // Visual warning logic
  const isWarning = tokenProgress >= 80 && tokenProgress < 95;
  const isCritical = tokenProgress >= 95;

  // ETA & burn rate calculation
  const hasSufficientData = goal.timeUsedSeconds >= 60 && goal.tokensUsed > 0;
  const burnRate = hasSufficientData ? (goal.tokensUsed / goal.timeUsedSeconds) * 60 : 0;
  const costRate =
    hasSufficientData && goal.costUsd && goal.costUsd > 0 ? (goal.costUsd / goal.timeUsedSeconds) * 60 : 0;

  const computeEtaSeconds = (): number | null => {
    if (!hasSufficientData || isTerminal || goal.status === 'budget_limited') return null;
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
  };

  const etaSeconds = computeEtaSeconds();

  const formatEta = (seconds: number): string => {
    if (seconds < 60) return '< 1min';
    if (seconds < 3600) return `~${Math.round(seconds / 60)}min`;
    const h = Math.floor(seconds / 3600);
    const m = Math.round((seconds % 3600) / 60);
    return `~${h}h ${m}m`;
  };

  const formatBurnRate = (tokPerMin: number): string => {
    if (tokPerMin >= 1000) return `~${(tokPerMin / 1000).toFixed(1)}K/min`;
    return `~${Math.round(tokPerMin)}/min`;
  };

  const getProgressColor = () => {
    if (isCritical) return 'bg-red-500';
    if (isWarning) return 'bg-orange-500';
    return 'bg-primary';
  };

  const displayReason = translateGoalReason(goal.reason, t);

  return (
    <>
      <div className="fixed top-16 left-1/2 -translate-x-1/2 z-50 w-[min(100%,28rem)] px-3 sm:px-4">
      <div className="bg-card border rounded-lg shadow-md overflow-hidden transition-all duration-200">
        {/* Header / Summary Row */}
        <div
          className="p-3 flex items-center justify-between cursor-pointer hover:bg-muted/50"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="flex-shrink-0">{getStatusIcon()}</div>
            <div className="flex flex-col overflow-hidden">
              <span className="text-sm font-medium truncate flex items-center gap-2">
                <GoalIcon className="h-3 w-3 text-muted-foreground" />
                {goal.uiSummary ||
                  (goal.objective.length > 120 ? goal.objective.slice(0, 120) + '...' : goal.objective)}
                {gitBranch && (
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
                      <line x1="6" y1="3" x2="6" y2="15"></line>
                      <circle cx="18" cy="6" r="3"></circle>
                      <circle cx="6" cy="18" r="3"></circle>
                      <path d="M18 9a9 9 0 0 1-9 9"></path>
                    </svg>
                    {gitBranch}
                  </span>
                )}
              </span>
              <span className="text-xs text-muted-foreground flex items-center gap-2">
                <span
                  data-testid="goal-status-badge"
                  className={goal.status === 'budget_limited' ? 'text-red-500 font-semibold' : ''}
                >
                  {getStatusText()}
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
                      className={
                        isCritical ? 'text-red-500 font-medium' : isWarning ? 'text-orange-500 font-medium' : ''
                      }
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

          {/* Action Buttons */}
          {!isTerminal && (
            <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
              {goal.status === 'wait' ? (
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleAction('unwait')}>
                  <PlayIcon className="h-4 w-4" />
                </Button>
              ) : goal.status === 'active' ? (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  data-testid="goal-pause-trigger"
                  onClick={() => setPauseDialogOpen(true)}
                >
                  <PauseIcon className="h-4 w-4" />
                </Button>
              ) : (
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleAction('resume')}>
                  <PlayIcon className="h-4 w-4" />
                </Button>
              )}
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-destructive hover:text-destructive"
                onClick={() => handleAction('cancel')}
              >
                <XCircleIcon className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>

        {/* Expanded Details */}
        {isExpanded && (
          <div className="p-3 pt-0 border-t bg-muted/20">
            <div className="mt-3 space-y-3">
              {/* Objective Section with Inline Edit */}
              <div className="border-b border-border/50 pb-3">
                {isEditingObjective ? (
                  <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
                    <textarea
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
                      rows={3}
                      maxLength={2000}
                      value={editedObjective}
                      onChange={(e) => setEditedObjective(e.target.value)}
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSaveObjective();
                        if (e.key === 'Escape') handleCancelEditObjective();
                      }}
                    />
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-muted-foreground">{editedObjective.length}/2000</span>
                      <div className="flex gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 px-2 text-xs"
                          onClick={handleCancelEditObjective}
                          disabled={isSavingObjective}
                        >
                          {t('cancel')}
                        </Button>
                        <Button
                          size="sm"
                          className="h-6 px-2 text-xs"
                          onClick={handleSaveObjective}
                          disabled={isSavingObjective || !editedObjective.trim()}
                        >
                          {isSavingObjective ? '...' : t('save')}
                        </Button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start gap-2 group/obj">
                    <p className="text-xs text-foreground/80 leading-relaxed flex-1 break-words">{goal.objective}</p>
                    {canEditObjective && (
                      <button
                        className="flex-shrink-0 mt-0.5 p-1 rounded hover:bg-muted transition-colors opacity-60 sm:opacity-0 sm:group-hover/obj:opacity-100"
                        onClick={handleStartEditObjective}
                        title={t('editObjective')}
                      >
                        <svg
                          className="h-3 w-3 text-muted-foreground"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
                          <path d="m15 5 4 4" />
                        </svg>
                      </button>
                    )}
                  </div>
                )}
              </div>

              {goal.budget?.maxTokens && (
                <div className="space-y-1">
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span className={isCritical ? 'text-red-500' : isWarning ? 'text-orange-500' : ''}>
                      {t('tokenUsage')} {isWarning && !isCritical && ' (Warning)'} {isCritical && ' (Critical)'}
                    </span>
                    <span
                      className={isCritical ? 'text-red-500 font-bold' : isWarning ? 'text-orange-500 font-bold' : ''}
                    >
                      {Math.round(tokenProgress)}%
                    </span>
                  </div>
                  <Progress
                    value={tokenProgress}
                    className={`h-1.5 ${isCritical ? 'animate-pulse' : ''}`}
                    indicatorClassName={getProgressColor()}
                  />
                </div>
              )}
              {goal.budget?.maxTurns && goal.turnsUsed !== undefined && (
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>{t('turnsUsed') || 'Turns'}</span>
                  <span>
                    {goal.turnsUsed} / {goal.budget.maxTurns}
                  </span>
                </div>
              )}
              <div className="flex justify-between items-center text-xs text-muted-foreground">
                <span>
                  {t('timeElapsed')}: {Math.floor(goal.timeUsedSeconds / 60)}m {goal.timeUsedSeconds % 60}s
                </span>

                {/* Notification Permission Request */}
                {notificationService.isSupported && notificationPermission !== 'granted' && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs text-muted-foreground hover:text-foreground"
                    onClick={handleRequestNotification}
                  >
                    <BellIcon className="h-3 w-3 mr-1" />
                    {t('enableBackgroundNotification')}
                  </Button>
                )}
              </div>

              {hasSufficientData && !isTerminal && (
                <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                  <span>
                    {t('burnRate')}: {formatBurnRate(burnRate)}
                  </span>
                  {etaSeconds !== null && (
                    <span>
                      {t('etaLabel')}: {formatEta(etaSeconds)}
                    </span>
                  )}
                  {costRate > 0 && <span>~${costRate.toFixed(3)}/min</span>}
                </div>
              )}

              {/* Constraints Section */}
              {goal.constraints && goal.constraints.length > 0 && (
                <div className="mt-3 border-t border-border/50 pt-3">
                  <span className="text-xs font-medium text-destructive/80">{t('constraintsLabel')}</span>
                  <ul className="mt-1.5 space-y-1">
                    {goal.constraints.map((c: string, idx: number) => (
                      <li
                        key={idx}
                        className="flex items-start gap-2 text-xs bg-destructive/5 p-1.5 rounded-lg border border-destructive/10"
                      >
                        <span className="flex-shrink-0 mt-0.5 text-destructive/60">
                          <svg
                            className="h-3 w-3"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2.5"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <circle cx="12" cy="12" r="10" />
                            <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
                          </svg>
                        </span>
                        <span className="text-destructive/80 break-words leading-relaxed">{c}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Acceptance Criteria Section with Live Results */}
              {goal.acceptanceCriteria && goal.acceptanceCriteria.length > 0 && (
                <AcceptanceCriteriaPanel
                  criteria={goal.acceptanceCriteria}
                  results={goal.acceptanceResults}
                  history={goal.acceptanceHistory}
                  t={t}
                />
              )}

              {/* Subgoals Section */}
              <div className="mt-4 border-t border-border/50 pt-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-foreground">{t('subgoals') || 'Subgoals'}</span>
                </div>
                {goal.subgoals && goal.subgoals.length > 0 && (
                  <ul className="space-y-1.5 mb-3">
                    {goal.subgoals.map((sg, idx) => (
                      <li
                        key={idx}
                        className="flex items-start gap-2 text-xs bg-background/50 p-2 rounded-lg border border-border/50 group"
                      >
                        <div className="flex-shrink-0 mt-0.5">
                          <CheckCircleIcon className="h-3.5 w-3.5 text-muted-foreground" />
                        </div>
                        <span className="flex-1 text-muted-foreground break-words leading-relaxed">{sg.text}</span>
                        {!isTerminal && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRemoveSubgoal(idx);
                            }}
                            className="text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
                            aria-label="Remove subgoal"
                          >
                            <XCircleIcon className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
                {!isTerminal && (
                  <div className="flex gap-2">
                    <Input
                      placeholder={t('subgoalPlaceholder') || 'Add acceptance criteria or sub-task...'}
                      className="h-8 text-xs bg-background/50 border-border/50"
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          const val = e.currentTarget.value;
                          handleAddSubgoal(val);
                          e.currentTarget.value = '';
                        }
                      }}
                    />
                    <Button
                      size="sm"
                      variant="secondary"
                      className="h-8 px-3 shrink-0 text-xs"
                      onClick={(e) => {
                        e.stopPropagation();
                        const input = e.currentTarget.previousElementSibling as HTMLInputElement;
                        const val = input?.value || '';
                        handleAddSubgoal(val);
                        if (input) input.value = '';
                      }}
                    >
                      {t('addSubgoal') || 'Add'}
                    </Button>
                  </div>
                )}
              </div>

              {/* Budget Limited Action */}
              {goal.status === 'budget_limited' && (
                <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <AlertIcon className="h-4 w-4 text-red-600" />
                    <p className="text-sm text-red-600 font-medium">{t('budgetExhaustedMessage')}</p>
                  </div>
                  <div className="flex gap-2 items-center">
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full border-red-200 hover:bg-red-50"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (chatId) {
                          useGoalStore
                            .getState()
                            .updateGoalBudget(chatId, 10000)
                            .then(() => {
                              handleAction('resume');
                            });
                        }
                      }}
                    >
                      {t('addTokensAndResume')}
                    </Button>
                  </div>
                </div>
              )}
              {/* Needs Human Review Action */}
              {goal.status === 'needs_human_review' && (
                <div className="mt-4 p-3 bg-orange-500/10 border border-orange-500/20 rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <AlertIcon className="h-4 w-4 text-orange-600" />
                    <p className="text-sm text-orange-600 font-medium">{t('reviewFailedMessage')}</p>
                  </div>
                  <p className="text-xs text-orange-600/80 mb-3">{t('reviewFailedHint')}</p>
                  <div className="flex flex-col gap-2">
                    <div className="flex gap-2">
                      <Input
                        placeholder={t('feedbackPlaceholder')}
                        className="h-8 text-xs bg-background/50 border-orange-200 focus-visible:ring-orange-500"
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            const val = e.currentTarget.value || '';
                            const msg = val.trim() ? val : t('resetRetriesMessage');
                            useChatStore.getState().sendMessage(msg);
                            handleAction('reject');
                            e.currentTarget.value = '';
                          }
                        }}
                      />
                      <Button
                        size="sm"
                        variant="outline"
                        className="border-orange-200 hover:bg-orange-50 text-orange-700 shrink-0"
                        onClick={(e) => {
                          e.stopPropagation();
                          const input = e.currentTarget.previousElementSibling as HTMLInputElement;
                          const val = input?.value || '';
                          const msg = val.trim() ? val : t('resetRetriesMessage');
                          useChatStore.getState().sendMessage(msg);
                          handleAction('reject');
                          if (input) input.value = '';
                        }}
                      >
                        {t('rejectAndRetry')}
                      </Button>
                    </div>
                    <Button
                      size="sm"
                      className="w-full bg-green-500 hover:bg-green-600 text-white"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleAction('approve');
                      }}
                    >
                      <CheckCircleIcon className="h-4 w-4 mr-1" />
                      {t('forceApprove')}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>

      <Dialog open={pauseDialogOpen} onOpenChange={setPauseDialogOpen}>
        <DialogContent className="sm:max-w-md" onClick={(e) => e.stopPropagation()}>
          <DialogHeader>
            <DialogTitle>{t('pauseDialogTitle')}</DialogTitle>
            <DialogDescription>{t('pauseDialogDescription')}</DialogDescription>
          </DialogHeader>
          <Input
            data-testid="goal-pause-note"
            value={pauseNote}
            onChange={(e) => setPauseNote(e.target.value)}
            placeholder={t('pauseNotePlaceholder')}
            className="text-sm"
            maxLength={500}
          />
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="ghost" onClick={() => setPauseDialogOpen(false)} disabled={isPausing}>
              {t('cancel')}
            </Button>
            <Button data-testid="goal-pause-confirm" onClick={handleConfirmPause} disabled={isPausing}>
              {isPausing ? t('pauseSubmitting') : t('pauseConfirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
