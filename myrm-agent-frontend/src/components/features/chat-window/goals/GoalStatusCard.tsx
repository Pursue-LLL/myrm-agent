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
import { isRiskHeldError, riskHeldErrorFromResponse } from '@/services/riskHeldToast';
import { GoalStatusHeader } from './GoalStatusHeader';
import { GoalStatusExpanded } from './GoalStatusExpanded';
import { GoalUsageLimitRow } from './GoalUsageLimitRow';
import type { GoalAction, GoalStatus } from './goalStatusTypes';
import { translateGoalReason, computeEtaSeconds } from './goalStatusUtils';
import { useGoalSync } from './useGoalSync';

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

  useGoalSync(chatId);

  useEffect(() => {
    setNotificationPermission(notificationService.permission);
  }, [chatId]);

  useEffect(() => {
    const handleBranchSwitched = (e: CustomEvent) => {
      const data = e.detail;
      if (chatId && data.chat_id === chatId) {
        useGoalStore.getState().setGitBranch(chatId, data.branch);
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

  if (!goal || !chatId) {
    return null;
  }

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
      if (!isRiskHeldError(err)) {
        toast.error(t('objectiveUpdateFailed'));
      }
      console.error('Failed to update objective:', err);
    } finally {
      setIsSavingObjective(false);
    }
  };

  /** Resolves whether the server took the action; a held note or a failure leaves the goal as it was. */
  const handleAction = async (action: GoalAction, note?: string): Promise<boolean> => {
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
        if (!(await riskHeldErrorFromResponse(res))) {
          toast.error(t(`goalActionFailed_${action}` as 'goalActionFailed_pause'));
        }
        return false;
      }
      toast.success(t(`goalActionSuccess_${action}` as 'goalActionSuccess_pause'));

      const statusMap: Record<string, GoalStatus> = {
        pause: 'paused',
        resume: 'active',
        reject: 'active',
        unwait: 'active',
        cancel: 'cancelled',
        approve: 'complete',
      };
      // Only a pause note is a status reason; the note of a rejected review is the agent's next message.
      const reason = action === 'pause' ? note?.trim() || undefined : undefined;
      // A chat opened while the request was out is not this chat: the store drops a status that is no longer its own.
      useGoalStore.getState().updateGoalStatus(chatId, statusMap[action] ?? goal.status, reason);
      return true;
    } catch (e) {
      console.error(`Network error: failed to ${action} goal`, e);
      toast.error(t(`goalActionFailed_${action}` as 'goalActionFailed_pause'));
      return false;
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

  /** Resolves whether the server took the sub-goal, so the input can keep a text that was not taken. */
  const handleAddSubgoal = async (text: string): Promise<boolean> => {
    if (!text.trim()) {
      return false;
    }
    try {
      const res = await fetchWithTimeout(`/goals/${chatId}/subgoals`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) {
        if (!(await riskHeldErrorFromResponse(res))) {
          toast.error(t('subgoalAddFailed'));
        }
        return false;
      }
      toast.success(t('subgoalAdded'));
      return true;
    } catch (e) {
      console.error('Failed to add subgoal', e);
      toast.error(t('subgoalAddNetworkError'));
      return false;
    }
  };

  const handleRemoveSubgoal = async (index: number) => {
    try {
      const res = await fetchWithTimeout(`/goals/${chatId}/subgoals/${index}`, { method: 'DELETE' });
      if (!res.ok) {
        toast.error(t('subgoalRemoveFailed'));
        return;
      }
      toast.success(t('subgoalRemoved'));
    } catch (e) {
      console.error('Failed to remove subgoal', e);
      toast.error(t('subgoalRemoveNetworkError'));
    }
  };

  const tokenProgress = goal.budget?.maxTokens ? (goal.tokensUsed / goal.budget.maxTokens) * 100 : 0;
  const isTerminal = goal.status === 'complete' || goal.status === 'cancelled';
  const isWarning = tokenProgress >= 80 && tokenProgress < 95;
  const isCritical = tokenProgress >= 95;
  const hasSufficientData = goal.timeUsedSeconds >= 60 && goal.tokensUsed > 0;
  const burnRate = hasSufficientData ? (goal.tokensUsed / goal.timeUsedSeconds) * 60 : 0;
  const costRate =
    hasSufficientData && goal.costUsd && goal.costUsd > 0 ? (goal.costUsd / goal.timeUsedSeconds) * 60 : 0;
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
          {goal.usageLimit && (
            <GoalUsageLimitRow status={goal.status} resumeAt={goal.usageLimit.resumeAt} onAction={handleAction} />
          )}
          {isExpanded && (
            <GoalStatusExpanded
              goal={goal}
              chatId={chatId}
              isTerminal={isTerminal}
              tokenProgress={tokenProgress}
              isWarning={isWarning}
              isCritical={isCritical}
              hasSufficientData={hasSufficientData}
              burnRate={burnRate}
              costRate={costRate}
              etaSeconds={etaSeconds}
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
