import React from 'react';
import { useTranslations } from 'next-intl';
import { ScrollArea } from '@/components/primitives/scroll-area';
import useChatStore from '@/store/useChatStore';
import { usePlanStore } from '@/store/chat/goals/usePlanStore';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { GoalQueueSection } from './GoalQueueSection';
import { GoalPlanStepsList } from './GoalPlanStepsList';
import { useGoalPlanSync } from './useGoalPlanSync';

const CheckCircleIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <path d="M22 4L12 14.01l-3-3" />
  </svg>
);

const XCircleIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <circle cx="12" cy="12" r="10" />
    <path d="m15 9-6 6" />
    <path d="m9 9 6 6" />
  </svg>
);

export const GoalControlPlane = () => {
  const t = useTranslations('Goal');
  const chatId = useChatStore((s) => s.chatId);
  const { plan } = usePlanStore();
  const activeGoal = useGoalStore((s) => s.activeGoal);

  useGoalPlanSync(chatId);

  if (!plan) {
    return null;
  }

  return (
    <div className="flex flex-col h-full border-l border-border bg-background/50 backdrop-blur-sm w-72 lg:w-80 shrink-0">
      <ScrollArea className="flex-1">
        <GoalPlanStepsList goal={plan.goal} steps={plan.steps} />

        <div className="px-4 pb-4 space-y-4">
          {activeGoal?.executionSummary &&
            (() => {
              const summary = activeGoal.executionSummary;
              const isBudgetCut = activeGoal.verdict === 'budget';
              const accentBg = isBudgetCut
                ? 'bg-amber-500/10 border-amber-500/20'
                : 'bg-emerald-500/10 border-emerald-500/20';
              const accentText = isBudgetCut ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400';

              const formatDuration = (seconds: number) => {
                if (seconds >= 3600) {
                  const hours = Math.floor(seconds / 3600);
                  const minutes = Math.round((seconds % 3600) / 60);
                  return minutes > 0 ? `${hours}h ${minutes}min` : `${hours}h`;
                }
                return seconds >= 60 ? `${Math.round(seconds / 60)}min` : `${Math.round(seconds)}s`;
              };

              return (
                <div className={`p-3 rounded-2xl border ${accentBg}`}>
                  <div className="flex items-center gap-2 mb-3">
                    {isBudgetCut ? (
                      <XCircleIcon className={`w-4 h-4 ${accentText}`} />
                    ) : (
                      <CheckCircleIcon className={`w-4 h-4 ${accentText}`} />
                    )}
                    <span className={`${accentText} text-sm font-semibold`}>{t('executionSummary')}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="p-2 rounded-xl bg-background/60 border border-border/50">
                      <span className="text-muted-foreground">{t('filesModified')}</span>
                      <p className="font-semibold text-foreground mt-0.5">{summary.files_modified.length}</p>
                    </div>
                    <div className="p-2 rounded-xl bg-background/60 border border-border/50">
                      <span className="text-muted-foreground">{t('verifications')}</span>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        {activeGoal.acceptanceResults && activeGoal.acceptanceResults.length > 0 ? (
                          <>
                            <span
                              className={`font-semibold ${
                                activeGoal.acceptanceResults.every((r) => r.passed)
                                  ? 'text-green-600 dark:text-green-400'
                                  : 'text-orange-600 dark:text-orange-400'
                              }`}
                            >
                              {activeGoal.acceptanceResults.filter((r) => r.passed).length}/
                              {activeGoal.acceptanceResults.length}
                            </span>
                          </>
                        ) : summary.verifications.length > 0 ? (
                          <span className="font-semibold text-foreground">
                            {summary.verifications.filter((v) => v.passed).length}/{summary.verifications.length}
                          </span>
                        ) : (
                          <span className="font-semibold text-foreground">-</span>
                        )}
                      </div>
                    </div>
                    <div className="p-2 rounded-xl bg-background/60 border border-border/50">
                      <span className="text-muted-foreground">{t('tokenCost')}</span>
                      <p className="font-semibold text-foreground mt-0.5">
                        {(summary.total_tokens / 1000).toFixed(1)}K / ${summary.total_cost_usd.toFixed(2)}
                      </p>
                    </div>
                    <div className="p-2 rounded-xl bg-background/60 border border-border/50">
                      <span className="text-muted-foreground">{t('duration')}</span>
                      <p className="font-semibold text-foreground mt-0.5">
                        {formatDuration(summary.execution_duration_s)}
                      </p>
                    </div>
                  </div>
                  {summary.files_modified.length > 0 && (
                    <details className="mt-2">
                      <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground transition-colors">
                        {t('viewFiles')}
                      </summary>
                      <ul className="mt-1.5 space-y-0.5 text-[11px] text-muted-foreground font-mono">
                        {summary.files_modified.map((filePath, index) => (
                          <li key={index} className="truncate">
                            • {filePath.split('/').slice(-2).join('/')}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              );
            })()}

          <GoalQueueSection />
        </div>
      </ScrollArea>
    </div>
  );
};
