import React, { useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { ScrollArea } from '@/components/primitives/scroll-area';
import useChatStore from '@/store/useChatStore';
import { usePlanStore } from '@/store/chat/goals/usePlanStore';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { GoalQueueSection } from './GoalQueueSection';

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

const CircleIcon = ({ className = 'w-4 h-4' }) => (
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
  </svg>
);

const LoaderIcon = ({ className = 'w-4 h-4' }) => (
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
    <path d="M21 12a9 9 0 1 1-6.219-8.56" />
  </svg>
);

const ListTodoIcon = ({ className = 'w-4 h-4' }) => (
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
    <rect x="3" y="5" width="6" height="6" rx="1" />
    <path d="m3 17 2 2 4-4" />
    <path d="M13 6h8" />
    <path d="M13 12h8" />
    <path d="M13 18h8" />
  </svg>
);

export const GoalControlPlane = () => {
  const t = useTranslations('Goal');
  const chatId = useChatStore((s) => s.chatId);
  const { plan, isLoading, fetchPlan, updateStepStatus } = usePlanStore();
  const activeGoal = useGoalStore((s) => s.activeGoal);

  useEffect(() => {
    if (!chatId) return;

    fetchPlan(chatId);

    const handlePlanUpdate = (event: Event) => {
      const detail = (event as CustomEvent).detail as {
        chat_id?: string;
        type?: string;
        step_key?: string;
        status?: string;
      } | null;
      if (!detail || detail.chat_id !== chatId || detail.type !== 'tasks_steps') {
        return;
      }

      const stepKey = detail.step_key;
      if (stepKey?.startsWith('todo_step_')) {
        const stepId = stepKey.replace('todo_step_', '');
        let status: 'pending' | 'in_progress' | 'completed' | 'skipped' = 'pending';
        if (detail.status === 'success') status = 'completed';
        else if (detail.status === 'running') status = 'in_progress';
        else if (detail.status === 'skipped') status = 'skipped';
        updateStepStatus(stepId, status);
        return;
      }

      if (stepKey === 'progress_root') {
        fetchPlan(chatId);
      }
    };

    window.addEventListener('tasks_steps', handlePlanUpdate);
    return () => window.removeEventListener('tasks_steps', handlePlanUpdate);
  }, [chatId, fetchPlan, updateStepStatus]);

  if (!plan) {
    if (isLoading) {
      return (
        <div className="flex flex-col h-full border-l bg-background/50 backdrop-blur-sm w-80 shrink-0 items-center justify-center">
          <LoaderIcon className="w-6 h-6 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground mt-2">{t('loadingProgress')}</p>
        </div>
      );
    }
    return null;
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircleIcon className="w-4 h-4 text-green-500" />;
      case 'in_progress':
        return <LoaderIcon className="w-4 h-4 text-blue-500 animate-spin" />;
      case 'skipped':
        return <XCircleIcon className="w-4 h-4 text-gray-400" />;
      default:
        return <CircleIcon className="w-4 h-4 text-gray-300" />;
    }
  };

  return (
    <div className="flex flex-col h-full border-l bg-background/50 backdrop-blur-sm w-80 shrink-0">
      <div className="p-4 border-b bg-card">
        <div className="flex items-center gap-2 mb-2">
          <ListTodoIcon className="w-5 h-5 text-primary" />
          <h3 className="font-semibold">{t('goalPlan')}</h3>
        </div>
        <p className="text-sm font-medium text-foreground">{plan.goal}</p>
      </div>

      <ScrollArea className="flex-1 p-4">
        <div className="space-y-4">
          {plan.steps.map((step, index) => (
            <div
              key={step.step_id}
              className={`p-3 rounded-lg border text-sm transition-colors ${
                step.status === 'in_progress'
                  ? 'bg-blue-50/50 border-blue-200 dark:bg-blue-900/20 dark:border-blue-800'
                  : step.status === 'completed'
                    ? 'bg-green-50/30 border-green-100 dark:bg-green-900/10 dark:border-green-900/30'
                    : 'bg-card border-border'
              }`}
            >
              <div className="flex gap-3">
                <div className="mt-0.5 shrink-0">{getStatusIcon(step.status)}</div>
                <div className="flex-1 min-w-0">
                  <p
                    className={`font-medium ${step.status === 'completed' ? 'text-muted-foreground line-through' : 'text-foreground'}`}
                  >
                    {index + 1}. {step.description}
                  </p>
                </div>
              </div>
            </div>
          ))}

          {activeGoal?.executionSummary &&
            (() => {
              const summary = activeGoal.executionSummary;
              const isBudgetCut = activeGoal.verdict === 'budget';
              const accentBg = isBudgetCut
                ? 'bg-amber-50/30 border-amber-200/50 dark:bg-amber-900/10 dark:border-amber-900/30'
                : 'bg-emerald-50/30 border-emerald-200/50 dark:bg-emerald-900/10 dark:border-emerald-900/30';
              const accentText = isBudgetCut
                ? 'text-amber-600 dark:text-amber-500'
                : 'text-emerald-600 dark:text-emerald-500';

              const formatDuration = (seconds: number) => {
                if (seconds >= 3600) {
                  const hours = Math.floor(seconds / 3600);
                  const minutes = Math.round((seconds % 3600) / 60);
                  return minutes > 0 ? `${hours}h ${minutes}min` : `${hours}h`;
                }
                return seconds >= 60 ? `${Math.round(seconds / 60)}min` : `${Math.round(seconds)}s`;
              };

              return (
                <div className={`mt-6 p-3 rounded-lg border ${accentBg}`}>
                  <div className="flex items-center gap-2 mb-3">
                    {isBudgetCut ? (
                      <XCircleIcon className={`w-4 h-4 ${accentText}`} />
                    ) : (
                      <CheckCircleIcon className={`w-4 h-4 ${accentText}`} />
                    )}
                    <span className={`${accentText} text-sm font-semibold`}>{t('executionSummary')}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="p-2 rounded bg-background/60 border border-border/50">
                      <span className="text-muted-foreground">{t('filesModified')}</span>
                      <p className="font-semibold text-foreground mt-0.5">{summary.files_modified.length}</p>
                    </div>
                    <div className="p-2 rounded bg-background/60 border border-border/50">
                      <span className="text-muted-foreground">{t('verifications')}</span>
                      <p className="font-semibold text-foreground mt-0.5">
                        {summary.verifications.length > 0
                          ? `${summary.verifications.filter((v) => v.passed).length}/${summary.verifications.length}`
                          : '-'}
                      </p>
                    </div>
                    <div className="p-2 rounded bg-background/60 border border-border/50">
                      <span className="text-muted-foreground">{t('tokenCost')}</span>
                      <p className="font-semibold text-foreground mt-0.5">
                        {(summary.total_tokens / 1000).toFixed(1)}K / ${summary.total_cost_usd.toFixed(2)}
                      </p>
                    </div>
                    <div className="p-2 rounded bg-background/60 border border-border/50">
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
