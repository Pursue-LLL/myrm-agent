'use client';

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
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import useChatStore from '@/store/useChatStore';
import { fetchWithTimeout } from '@/lib/api';
import { toast } from 'sonner';
import { notificationService } from '@/services/notification';
import { PlayIcon, PauseIcon, XCircleIcon, CheckCircleIcon, AlertIcon, GoalIcon } from './goal-icons';
import { GoalStatusExpanded } from './GoalStatusExpanded';
import type { GoalStatus } from './goalStatusTypes';
import { translateGoalReason, computeEtaSeconds, formatEta, formatBurnRate, getProgressColor } from './goalStatusUtils';

export type { GoalStatus, GoalState, AcceptanceResultItem, AcceptanceHistoryEntry } from './goalStatusTypes';

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
    return () => window.removeEventListener('goal:branch_switched', handleBranchSwitched as EventListener);
  }, [chatId, t]);

  const handleRequestNotification = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const permission = await notificationService.requestPermission();
    setNotificationPermission(permission);
    toast[permission === 'granted' ? 'success' : 'error'](
      t(permission === 'granted' ? 'notificationEnabled' : 'notificationDenied'),
    );
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
      if (note?.trim()) payload.note = note.trim();
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

      const statusMap: Record<string, GoalStatus> = {
        pause: 'paused', resume: 'active', reject: 'active', unwait: 'active',
        cancel: 'cancelled', approve: 'complete',
      };
      useGoalStore.getState().updateGoalStatus(statusMap[action] ?? goal.status, note?.trim() || undefined);
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
      if (!res.ok) { toast.error('Failed to add subgoal'); return; }
      toast.success(t('subgoalAdded') || 'Subgoal added');
    } catch (e) {
      console.error('Failed to add subgoal', e);
      toast.error('Network error: failed to add subgoal');
    }
  };

  const handleRemoveSubgoal = async (index: number) => {
    try {
      const res = await fetchWithTimeout(`/goals/${chatId}/subgoals/${index}`, { method: 'DELETE' });
      if (!res.ok) { toast.error('Failed to remove subgoal'); return; }
      toast.success(t('subgoalRemoved') || 'Subgoal removed');
    } catch (e) {
      console.error('Failed to remove subgoal', e);
      toast.error('Network error: failed to remove subgoal');
    }
  };

  const tokenProgress = goal.budget?.maxTokens ? (goal.tokensUsed / goal.budget.maxTokens) * 100 : 0;
  const isTerminal = goal.status === 'complete' || goal.status === 'cancelled';
  const isWarning = tokenProgress >= 80 && tokenProgress < 95;
  const isCritical = tokenProgress >= 95;
  const hasSufficientData = goal.timeUsedSeconds >= 60 && goal.tokensUsed > 0;
  const burnRate = hasSufficientData ? (goal.tokensUsed / goal.timeUsedSeconds) * 60 : 0;
  const costRate = hasSufficientData && goal.costUsd && goal.costUsd > 0
    ? (goal.costUsd / goal.timeUsedSeconds) * 60 : 0;
  const etaSeconds = computeEtaSeconds(goal, hasSufficientData, isTerminal);
  const displayReason = translateGoalReason(goal.reason, t);

  return (
    <>
      <div className="fixed top-16 left-1/2 -translate-x-1/2 z-50 w-[min(100%,28rem)] px-3 sm:px-4">
        <div className="bg-card border rounded-lg shadow-md overflow-hidden transition-all duration-200">
          <GoalStatusHeader
            goal={goal}
            gitBranch={gitBranch}
            isTerminal={isTerminal}
            isWarning={isWarning}
            isCritical={isCritical}
            etaSeconds={etaSeconds}
            hasSufficientData={hasSufficientData}
            displayReason={displayReason}
            queueCount={queueCount}
            onToggleExpand={() => setIsExpanded(!isExpanded)}
            onPause={() => setPauseDialogOpen(true)}
            onAction={handleAction}
            t={t}
          />
          {isExpanded && (
            <GoalStatusExpanded
              goal={goal}
              chatId={chatId}
              isTerminal={isTerminal}
              tokenProgress={tokenProgress}
              isWarning={isWarning}
              isCritical={isCritical}
              getProgressColor={() => getProgressColor(isCritical, isWarning)}
              hasSufficientData={hasSufficientData}
              burnRate={burnRate}
              costRate={costRate}
              etaSeconds={etaSeconds}
              formatEta={formatEta}
              formatBurnRate={formatBurnRate}
              canEditObjective={canEditObjective}
              notificationPermission={notificationPermission}
              onRequestNotification={handleRequestNotification}
              onStartEditObjective={handleStartEditObjective}
              onCancelEditObjective={handleCancelEditObjective}
              onSaveObjective={handleSaveObjective}
              isEditingObjective={isEditingObjective}
              editedObjective={editedObjective}
              onEditedObjectiveChange={setEditedObjective}
              isSavingObjective={isSavingObjective}
              onAction={handleAction}
              onAddSubgoal={handleAddSubgoal}
              onRemoveSubgoal={handleRemoveSubgoal}
              t={t}
            />
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

function GoalStatusHeader({
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
  goal: NonNullable<ReturnType<typeof useGoalStore.getState>['activeGoal']>;
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
  onAction: (action: 'pause' | 'resume' | 'cancel' | 'approve' | 'reject' | 'unwait', note?: string) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const statusIcon = getStatusIcon(goal);
  const statusText = getStatusText(goal, t);

  return (
    <div className="p-3 flex items-center justify-between cursor-pointer hover:bg-muted/50" onClick={onToggleExpand}>
      <div className="flex items-center gap-3 overflow-hidden">
        <div className="flex-shrink-0">{statusIcon}</div>
        <div className="flex flex-col overflow-hidden">
          <span className="text-sm font-medium truncate flex items-center gap-2">
            <GoalIcon className="h-3 w-3 text-muted-foreground" />
            {goal.uiSummary || (goal.objective.length > 120 ? goal.objective.slice(0, 120) + '...' : goal.objective)}
            {gitBranch && <GitBranchBadge branch={gitBranch} />}
          </span>
          <span className="text-xs text-muted-foreground flex items-center gap-2">
            <span data-testid="goal-status-badge" className={goal.status === 'budget_limited' ? 'text-red-500 font-semibold' : ''}>
              {statusText}
            </span>
            {displayReason && (goal.status === 'paused' || goal.status === 'wait') && (
              <>
                <span>•</span>
                <span className={goal.status === 'wait' ? 'text-blue-600 dark:text-blue-400 italic' : 'text-yellow-600 dark:text-yellow-400 italic'}>
                  {displayReason}
                </span>
              </>
            )}
            {queueCount > 0 && <><span>•</span><span className="text-muted-foreground/70">+{queueCount} {t('queueTitle').toLowerCase()}</span></>}
            {goal.budget?.maxTokens && (
              <><span>•</span><span className={isCritical ? 'text-red-500 font-medium' : isWarning ? 'text-orange-500 font-medium' : ''}>
                {goal.tokensUsed.toLocaleString()} / {goal.budget.maxTokens.toLocaleString()} tokens
              </span></>
            )}
            {goal.budget?.maxTurns && goal.turnsUsed !== undefined && (
              <><span>•</span><span>{goal.turnsUsed}/{goal.budget.maxTurns} turns</span></>
            )}
            {goal.costUsd !== undefined && goal.costUsd > 0 && (
              <><span>•</span><span className="text-green-600 font-medium">${goal.costUsd.toFixed(4)}</span></>
            )}
            {etaSeconds !== null && <><span>•</span><span className="text-primary/80 font-medium">{formatEta(etaSeconds)}</span></>}
            {!hasSufficientData && goal.status === 'active' && goal.budget?.maxTokens && (
              <><span>•</span><span className="text-muted-foreground/60 italic">{t('etaCollecting')}</span></>
            )}
          </span>
        </div>
      </div>

      {!isTerminal && (
        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          {goal.status === 'wait' ? (
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onAction('unwait')}><PlayIcon className="h-4 w-4" /></Button>
          ) : goal.status === 'active' ? (
            <Button variant="ghost" size="icon" className="h-8 w-8" data-testid="goal-pause-trigger" onClick={onPause}><PauseIcon className="h-4 w-4" /></Button>
          ) : (
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onAction('resume')}><PlayIcon className="h-4 w-4" /></Button>
          )}
          <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => onAction('cancel')}>
            <XCircleIcon className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}

function GitBranchBadge({ branch }: { branch: string }) {
  return (
    <span className="ml-1 inline-flex items-center rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground border">
      <svg className="w-3 h-3 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="6" y1="3" x2="6" y2="15" /><circle cx="18" cy="6" r="3" /><circle cx="6" cy="18" r="3" /><path d="M18 9a9 9 0 0 1-9 9" />
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

function getStatusText(goal: { status: GoalStatus; verdict?: string; reason?: string; loopRestarts?: number }, t: (key: string) => string) {
  switch (goal.status) {
    case 'active':
      if (goal.verdict === 'loop_restart') return `${t('statusLoopRestart')} (#${goal.loopRestarts ?? 0})`;
      return t('statusActive');
    case 'paused':
      if (goal.verdict === 'drift_pause') return goal.reason?.startsWith('Sandbox boundary') ? t('statusSandboxPaused') : t('statusDriftPaused');
      return t('statusPaused');
    case 'wait': return t('statusWait');
    case 'needs_human_review': return t('statusNeedsHumanReview') || 'Needs Human Review';
    case 'budget_limited': return t('statusBudgetLimited');
    case 'complete': return goal.verdict === 'convergence' ? t('statusConverged') : t('statusComplete');
    case 'cancelled': return t('statusCancelled');
  }
}
