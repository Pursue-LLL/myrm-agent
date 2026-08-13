'use client';

import type { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Progress } from '@/components/primitives/progress';
import { usePlanStore } from '@/store/chat/goals/usePlanStore';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import useChatStore from '@/store/useChatStore';
import { AcceptanceCriteriaPanel } from './AcceptanceCriteriaPanel';
import { CheckCircleIcon, XCircleIcon, AlertIcon, BellIcon } from './goal-icons';
import type { GoalState } from './goalStatusTypes';
import { formatEta, formatBurnRate, getProgressColor } from './goalStatusUtils';
import { notificationService } from '@/services/notification';
import { TaskDeliverableBundle } from './TaskDeliverableBundle';

interface GoalStatusExpandedProps {
  goal: GoalState;
  chatId: string;
  isTerminal: boolean;
  tokenProgress: number;
  isWarning: boolean;
  isCritical: boolean;
  hasSufficientData: boolean;
  burnRate: number;
  costRate: number;
  etaSeconds: number | null;
  canEditObjective: boolean;
  notificationPermission: NotificationPermission;
  onRequestNotification: (e: React.MouseEvent) => void;
  onStartEditObjective: (e: React.MouseEvent) => void;
  onCancelEditObjective: () => void;
  onSaveObjective: () => void;
  isEditingObjective: boolean;
  editedObjective: string;
  onEditedObjectiveChange: (value: string) => void;
  isSavingObjective: boolean;
  onAction: (action: 'pause' | 'resume' | 'cancel' | 'approve' | 'reject' | 'unwait', note?: string) => void;
  onAddSubgoal: (text: string) => void;
  onRemoveSubgoal: (index: number) => void;
  t: ReturnType<typeof useTranslations>;
}

export function GoalStatusExpanded({
  goal,
  chatId,
  isTerminal,
  tokenProgress,
  isWarning,
  isCritical,
  hasSufficientData,
  burnRate,
  costRate,
  etaSeconds,
  canEditObjective,
  notificationPermission,
  onRequestNotification,
  onStartEditObjective,
  onCancelEditObjective,
  onSaveObjective,
  isEditingObjective,
  editedObjective,
  onEditedObjectiveChange,
  isSavingObjective,
  onAction,
  onAddSubgoal,
  onRemoveSubgoal,
  t,
}: GoalStatusExpandedProps) {
  const plan = usePlanStore((s) => s.plan);

  const completedSteps = plan?.steps.filter((s) => s.status === 'completed' || s.status === 'skipped').length ?? 0;
  const totalSteps = plan?.steps.length ?? 0;
  const stepProgress = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0;

  return (
    <div className="p-3 pt-0 border-t bg-muted/20">
      <div className="mt-3 space-y-3">
        {/* Objective Section with Inline Edit */}
        <div className="border-b border-border/50 pb-3">
          {isEditingObjective ? (
            <ObjectiveEditor
              editedObjective={editedObjective}
              onEditedObjectiveChange={onEditedObjectiveChange}
              onSaveObjective={onSaveObjective}
              onCancelEditObjective={onCancelEditObjective}
              isSavingObjective={isSavingObjective}
              t={t}
            />
          ) : (
            <div className="flex items-start gap-2 group/obj">
              <p className="text-xs text-foreground/80 leading-relaxed flex-1 break-words">{goal.objective}</p>
              {canEditObjective && (
                <button
                  className="flex-shrink-0 mt-0.5 p-1 rounded hover:bg-muted transition-colors opacity-60 sm:opacity-0 sm:group-hover/obj:opacity-100"
                  onClick={onStartEditObjective}
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

        {/* Step Progress */}
        {plan && totalSteps > 0 && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{t('stepProgress')}</span>
              <span>{completedSteps}/{totalSteps} ({stepProgress}%)</span>
            </div>
            <Progress
              value={stepProgress}
              className="h-1.5"
              indicatorClassName={stepProgress === 100 ? 'bg-emerald-500' : 'bg-primary'}
            />
          </div>
        )}

        {/* Token Progress */}
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
              indicatorClassName={getProgressColor(isCritical, isWarning)}
            />
          </div>
        )}

        {/* Turns */}
        {goal.budget?.maxTurns && goal.turnsUsed !== undefined && (
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{t('turnsUsed') || 'Turns'}</span>
            <span>
              {goal.turnsUsed} / {goal.budget.maxTurns}
            </span>
          </div>
        )}

        {/* Time & Notification */}
        <div className="flex justify-between items-center text-xs text-muted-foreground">
          <span>
            {t('timeElapsed')}: {Math.floor(goal.timeUsedSeconds / 60)}m {goal.timeUsedSeconds % 60}s
          </span>
          {notificationService.isSupported && notificationPermission !== 'granted' && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs text-muted-foreground hover:text-foreground"
              onClick={onRequestNotification}
            >
              <BellIcon className="h-3 w-3 mr-1" />
              {t('enableBackgroundNotification')}
            </Button>
          )}
        </div>

        {/* Burn Rate & ETA */}
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

        {/* Constraints */}
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

        {/* Acceptance Criteria */}
        {goal.acceptanceCriteria && goal.acceptanceCriteria.length > 0 && (
          <AcceptanceCriteriaPanel
            criteria={goal.acceptanceCriteria}
            results={goal.acceptanceResults}
            history={goal.acceptanceHistory}
            t={t}
          />
        )}

        {/* Task Deliverable Bundle */}
        {isTerminal && goal.status === 'complete' && (
          <TaskDeliverableBundle goal={goal} chatId={chatId} />
        )}

        {/* Subgoals */}
        <SubgoalsSection
          goal={goal}
          chatId={chatId}
          isTerminal={isTerminal}
          onAddSubgoal={onAddSubgoal}
          onRemoveSubgoal={onRemoveSubgoal}
          t={t}
        />

        {/* Budget Limited Action */}
        {goal.status === 'budget_limited' && (
          <BudgetLimitedAction chatId={chatId} onAction={onAction} t={t} />
        )}

        {/* Needs Human Review Action */}
        {goal.status === 'needs_human_review' && (
          <HumanReviewAction onAction={onAction} t={t} />
        )}
      </div>
    </div>
  );
}

function ObjectiveEditor({
  editedObjective,
  onEditedObjectiveChange,
  onSaveObjective,
  onCancelEditObjective,
  isSavingObjective,
  t,
}: {
  editedObjective: string;
  onEditedObjectiveChange: (v: string) => void;
  onSaveObjective: () => void;
  onCancelEditObjective: () => void;
  isSavingObjective: boolean;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
      <textarea
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
        rows={3}
        maxLength={2000}
        value={editedObjective}
        onChange={(e) => onEditedObjectiveChange(e.target.value)}
        autoFocus
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {onSaveObjective();}
          if (e.key === 'Escape') {onCancelEditObjective();}
        }}
      />
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground">{editedObjective.length}/2000</span>
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={onCancelEditObjective}
            disabled={isSavingObjective}
          >
            {t('cancel')}
          </Button>
          <Button
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={onSaveObjective}
            disabled={isSavingObjective || !editedObjective.trim()}
          >
            {isSavingObjective ? '...' : t('save')}
          </Button>
        </div>
      </div>
    </div>
  );
}

function SubgoalsSection({
  goal,
  chatId: _chatId,
  isTerminal,
  onAddSubgoal,
  onRemoveSubgoal,
  t,
}: {
  goal: GoalState;
  chatId: string;
  isTerminal: boolean;
  onAddSubgoal: (text: string) => void;
  onRemoveSubgoal: (index: number) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
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
                    onRemoveSubgoal(idx);
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
                onAddSubgoal(val);
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
              onAddSubgoal(val);
              if (input) {input.value = '';}
            }}
          >
            {t('addSubgoal') || 'Add'}
          </Button>
        </div>
      )}
    </div>
  );
}

function BudgetLimitedAction({
  chatId,
  onAction,
  t,
}: {
  chatId: string;
  onAction: (action: 'resume', note?: string) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
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
            useGoalStore
              .getState()
              .updateGoalBudget(chatId, 10000)
              .then(() => {
                onAction('resume');
              });
          }}
        >
          {t('addTokensAndResume')}
        </Button>
      </div>
    </div>
  );
}

function HumanReviewAction({
  onAction,
  t,
}: {
  onAction: (action: 'approve' | 'reject', note?: string) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
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
                onAction('reject');
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
              onAction('reject');
              if (input) {input.value = '';}
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
            onAction('approve');
          }}
        >
          <CheckCircleIcon className="h-4 w-4 mr-1" />
          {t('forceApprove')}
        </Button>
      </div>
    </div>
  );
}
