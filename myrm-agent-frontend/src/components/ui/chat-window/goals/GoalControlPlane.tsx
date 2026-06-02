import React, { useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import useChatStore from '@/store/useChatStore';
import { usePlanStore } from '@/store/chat/goals/usePlanStore';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import KanbanGraphView from '@/components/ui/kanban/KanbanGraphView';
import type { KanbanTask, TaskDependency } from '@/services/kanban';
import { GoalQueueSection } from './GoalQueueSection';

// Premium SVG Icons
const PlayIcon = ({ className = 'w-4 h-4' }) => (
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
    <polygon points="6 3 20 12 6 21 6 3" />
  </svg>
);

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

const IdeaIcon = ({ className = 'w-4 h-4' }) => (
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
    <path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.9 1.2 1.5 1.5 2.5" />
    <path d="M9 18h6" />
    <path d="M10 22h4" />
  </svg>
);

const AlertTriangleIcon = ({ className = 'w-4 h-4' }) => (
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
    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />
    <path d="M12 9v4" />
    <path d="M12 17h.01" />
  </svg>
);

export const GoalControlPlane = () => {
  const t = useTranslations('Goal');
  const chatId = useChatStore((s) => s.chatId);
  const { plan, isApproved, isLoading, fetchPlan, approvePlan, updateStepStatus } = usePlanStore();
  const activeGoal = useGoalStore((s) => s.activeGoal);

  const [viewMode, setViewMode] = React.useState<'list' | 'graph'>('list');

  const mockTasks: KanbanTask[] = React.useMemo(() => {
    if (!plan?.steps) return [];
    return plan.steps.map((s) => ({
      task_id: s.step_id,
      board_id: 'goal-plan',
      title: s.description,
      description: s.expected_output || '',
      status: s.status === 'completed' ? 'completed' : s.status === 'in_progress' ? 'running' : 'backlog',
      priority: 'normal',
      retry_count: 0,
      max_retries: 3,
      consecutive_failures: 0,
      result: '',
      error: '',
      metadata: {},
      dep_count: s.dependencies.length,
      children_total: 0,
      children_done: 0,
      comment_count: 0,
      extra_skill_ids: [],
      attachment_ids: [],
      attachments: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }));
  }, [plan?.steps]);

  const mockEdges: TaskDependency[] = React.useMemo(() => {
    if (!plan?.steps) return [];
    const edges: TaskDependency[] = [];
    plan.steps.forEach((s) => {
      s.dependencies.forEach((dep) => {
        edges.push({
          parent_task_id: dep,
          child_task_id: s.step_id,
        });
      });
    });
    return edges;
  }, [plan?.steps]);

  useEffect(() => {
    if (!chatId) return;

    // Fetch the real plan from the server
    fetchPlan(chatId);

    // Listen for TASKS_STEPS events to update progress
    const handlePlanUpdate = (e: any) => {
      const detail = e.detail;
      // The TASKS_STEPS event from planner_tool emits step_key like "plan_step_step_1"
      if (detail && detail.chat_id === chatId && detail.type === 'tasks_steps') {
        const stepKey = detail.step_key;
        if (stepKey && stepKey.startsWith('plan_step_')) {
          const stepId = stepKey.replace('plan_step_', '');
          // Map UI status back to plan status
          let status: 'pending' | 'in_progress' | 'completed' | 'skipped' = 'pending';
          if (detail.status === 'success') status = 'completed';
          else if (detail.status === 'running') status = 'in_progress';
          else if (detail.status === 'skipped') status = 'skipped';

          updateStepStatus(stepId, status);
        } else if (stepKey === 'planner_root') {
          // Refresh the whole plan to get updated key_findings and notes
          fetchPlan(chatId);
        }
      }
    };

    window.addEventListener('tasks_steps', handlePlanUpdate);
    return () => window.removeEventListener('tasks_steps', handlePlanUpdate);
  }, [chatId, fetchPlan, updateStepStatus]);

  // Determine if we need approval based on goal status
  useEffect(() => {
    if (activeGoal && activeGoal.status === 'pending_approval') {
      usePlanStore.getState().setApproved(false);
    } else if (activeGoal && activeGoal.status === 'active') {
      usePlanStore.getState().setApproved(true);
    }
  }, [activeGoal]);

  if (!plan) {
    if (isLoading) {
      return (
        <div className="flex flex-col h-full border-l bg-background/50 backdrop-blur-sm w-80 shrink-0 items-center justify-center">
          <LoaderIcon className="w-6 h-6 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground mt-2">Loading plan...</p>
        </div>
      );
    }
    return null;
  }

  const handleApprove = async () => {
    if (!chatId) return;
    const success = await approvePlan(chatId);
    if (success) {
      // Optimistically update goal status
      useGoalStore.getState().updateGoalStatus('active');
    }
  };

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
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <ListTodoIcon className="w-5 h-5 text-primary" />
            <h3 className="font-semibold">{t('goalPlan')}</h3>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-xs px-2"
            onClick={() => setViewMode((v) => (v === 'list' ? 'graph' : 'list'))}
          >
            {viewMode === 'list' ? 'DAG View' : 'List View'}
          </Button>
        </div>
        <p className="text-sm font-medium text-foreground">{plan.goal}</p>
        <p className="text-xs text-muted-foreground mt-1 line-clamp-2" title={plan.reasoning}>
          {plan.reasoning}
        </p>
      </div>

      <ScrollArea className="flex-1 p-4">
        <div className="space-y-4">
          {viewMode === 'graph' ? (
            <div className="h-[500px] w-full rounded-lg border bg-background overflow-hidden relative">
              <KanbanGraphView tasks={mockTasks} edges={mockEdges} />
            </div>
          ) : (
            <>
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
                      <p className="text-xs text-muted-foreground mt-1">Output: {step.expected_output}</p>
                      {step.dependencies.length > 0 && (
                        <p className="text-[10px] text-muted-foreground/70 mt-1">
                          Deps: {step.dependencies.join(', ')}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </>
          )}

          {/* Pending Issues Section — only shown before approval */}
          {!isApproved && plan.pending_issues && plan.pending_issues.length > 0 && (
            <div className="mt-4 p-3 rounded-lg border bg-orange-50/40 border-orange-300/50 dark:bg-orange-900/10 dark:border-orange-800/40">
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangleIcon className="w-4 h-4 text-orange-600 dark:text-orange-400" />
                <span className="text-orange-600 dark:text-orange-400 text-sm font-semibold">{t('pendingIssues')}</span>
              </div>
              <ul className="space-y-1.5">
                {plan.pending_issues.map((issue, idx) => (
                  <li key={idx} className="text-xs text-foreground/80 flex gap-2">
                    <span className="text-orange-500/60 mt-0.5 shrink-0">•</span>
                    <span className="leading-relaxed">{issue}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Key Decisions Section */}
          {plan.decisions && plan.decisions.length > 0 && (
            <div className="mt-6 p-3 rounded-lg border bg-amber-50/30 border-amber-200/50 dark:bg-amber-900/10 dark:border-amber-900/30">
              <div className="flex items-center gap-2 mb-3">
                <IdeaIcon className="w-4 h-4 text-amber-600 dark:text-amber-500" />
                <span className="text-amber-600 dark:text-amber-500 text-sm font-semibold">
                  {t('architecturalDecisions')}
                </span>
              </div>
              <div className="space-y-3">
                {plan.decisions.map((decision, idx) => (
                  <div
                    key={decision.id || idx}
                    className={`p-2.5 rounded-full border text-xs ${
                      decision.status === 'active'
                        ? 'bg-background/80 border-amber-200/50 dark:border-amber-700/30'
                        : 'bg-background/40 border-border/50 opacity-70'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-1">
                      <span className="font-medium text-foreground">
                        {decision.topic}: {decision.decision}
                      </span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded-full shrink-0 ${
                          decision.status === 'active'
                            ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                            : 'bg-muted text-muted-foreground'
                        }`}
                      >
                        {decision.status}
                      </span>
                    </div>
                    <p className="text-muted-foreground leading-relaxed">{decision.rationale}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Legacy Key Findings Section (Fallback) */}
          {(!plan.decisions || plan.decisions.length === 0) && plan.key_findings && plan.key_findings.length > 0 && (
            <div className="mt-6 p-3 rounded-lg border bg-amber-50/30 border-amber-200/50 dark:bg-amber-900/10 dark:border-amber-900/30">
              <div className="flex items-center gap-2 mb-2">
                <IdeaIcon className="w-4 h-4 text-amber-600 dark:text-amber-500" />
                <span className="text-amber-600 dark:text-amber-500 text-sm font-semibold">{t('keyDecisions')}</span>
              </div>
              <ul className="space-y-1.5">
                {plan.key_findings.map((finding, idx) => (
                  <li key={idx} className="text-xs text-foreground/80 flex gap-2">
                    <span className="text-amber-500/50 mt-0.5">•</span>
                    <span className="leading-relaxed">{finding}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Execution Summary — shown when goal is terminal */}
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

              const formatDuration = (s: number) => {
                if (s >= 3600) {
                  const h = Math.floor(s / 3600);
                  const m = Math.round((s % 3600) / 60);
                  return m > 0 ? `${h}h ${m}min` : `${h}h`;
                }
                return s >= 60 ? `${Math.round(s / 60)}min` : `${Math.round(s)}s`;
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
                        {summary.files_modified.map((f, i) => (
                          <li key={i} className="truncate">
                            • {f.split('/').slice(-2).join('/')}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              );
            })()}

          {/* Goal Queue */}
          <GoalQueueSection />
        </div>
      </ScrollArea>

      {!isApproved && (
        <div className="p-4 border-t bg-card/80 backdrop-blur-md">
          <Button className="w-full gap-2" onClick={handleApprove}>
            <PlayIcon className="w-4 h-4" />
            {t('approveAndExecute')}
          </Button>
        </div>
      )}
    </div>
  );
};
