'use client';

import type { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Progress } from '@/components/primitives/progress';
import { usePlanStore } from '@/store/chat/goals/usePlanStore';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { AcceptanceCriteriaPanel } from './AcceptanceCriteriaPanel';
import { GoalHumanReviewAction } from './GoalHumanReviewAction';
import { GoalSubgoalsSection } from './GoalSubgoalsSection';
import { AlertIcon, BellIcon } from './goal-icons';
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
  onAction: (
    action: 'pause' | 'resume' | 'cancel' | 'approve' | 'reject' | 'unwait',
    note?: string,
  ) => Promise<boolean>;
  onAddSubgoal: (text: string) => Promise<boolean>;
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
                  className="flex-shrink-0 mt-0.5 p-1 rounded hover:bg-muted transition-colors opacity-0 group-hover/obj:opacity-100 group-focus-within/obj:opacity-100 pointer-coarse:opacity-100"
                  onClick={onStartEditObjective}
                  title={t('editObjective')}
                  aria-label={t('editObjective')}
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
              <span>
                {completedSteps}/{totalSteps} ({stepProgress}%)
              </span>
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
              <span className={isCritical ? 'text-red-500 font-bold' : isWarning ? 'text-orange-500 font-bold' : ''}>
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
        {isTerminal && goal.status === 'complete' && <TaskDeliverableBundle goal={goal} chatId={chatId} />}

        {/* Subgoals */}
        <GoalSubgoalsSection
          goal={goal}
          isTerminal={isTerminal}
          onAddSubgoal={onAddSubgoal}
          onRemoveSubgoal={onRemoveSubgoal}
          t={t}
        />

        {/* Budget Limited Action */}
        {goal.status === 'budget_limited' && <BudgetLimitedAction chatId={chatId} onAction={onAction} t={t} />}

        {/* Needs Human Review Action */}
        {goal.status === 'needs_human_review' && <GoalHumanReviewAction onAction={onAction} t={t} />}
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
    <div className="space-y-2" onClick={(e) => e.stopPropagation()} role="presentation">
      <textarea
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
        rows={3}
        maxLength={2000}
        value={editedObjective}
        onChange={(e) => onEditedObjectiveChange(e.target.value)}
        // oxlint-disable-next-line jsx-a11y/no-autofocus -- focus follows the user action that revealed this field
        autoFocus
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
            onSaveObjective();
          }
          if (e.key === 'Escape') {
            onCancelEditObjective();
          }
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
