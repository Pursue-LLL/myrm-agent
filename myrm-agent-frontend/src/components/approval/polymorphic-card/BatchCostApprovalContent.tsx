'use client';

import { useTranslations } from 'next-intl';
import { DollarSign, Layers } from 'lucide-react';
import type { ApprovalPayload } from '@/store/useApprovalStore';

/** Review body of a batch run's cost estimate: spend, task count, remaining budget and the tasks themselves. */
export function BatchCostApprovalContent({ approval }: { approval: ApprovalPayload }) {
  const t = useTranslations('toolApproval');
  const taskCount = (approval.payload?.task_count as number) || 0;
  const estimatedCost = (approval.payload?.estimated_cost_usd as number) || 0;
  const remainingBudget = approval.payload?.remaining_budget_usd as number | undefined;
  const costStatus = (approval.payload?.cost_status as string) || '';
  const isRace = Boolean(approval.payload?.race);
  const isTournament = Boolean(approval.payload?.tournament);
  const taskSummaries = (approval.payload?.tasks as Array<{ agent_type: string; objective: string }>) || [];

  const modeLabel = isTournament ? t('batchCostTournament') : isRace ? t('batchCostRace') : t('batchCostParallel');

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 px-4 py-3">
        <DollarSign className="h-5 w-5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
        <div>
          <h4 className="font-semibold text-sm text-amber-700 dark:text-amber-300">{t('batchCostTitle')}</h4>
          <p className="text-xs text-amber-600/80 dark:text-amber-400/80 mt-0.5">{t('batchCostDescription')}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border bg-muted/50 p-3 text-center">
          <div className="text-2xl font-bold text-foreground">${estimatedCost.toFixed(2)}</div>
          <div className="text-xs text-muted-foreground mt-1">{t('batchCostEstimated')}</div>
        </div>
        <div className="rounded-lg border bg-muted/50 p-3 text-center">
          <div className="text-2xl font-bold text-foreground">{taskCount}</div>
          <div className="text-xs text-muted-foreground mt-1">{t('batchCostTaskCount')}</div>
        </div>
      </div>

      {remainingBudget !== null && remainingBudget !== undefined && (
        <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2 text-sm">
          <span className="text-muted-foreground">{t('batchCostRemaining')}</span>
          <span className="font-mono font-medium">${remainingBudget.toFixed(2)}</span>
        </div>
      )}

      <div className="flex items-center gap-2 text-xs text-muted-foreground px-1">
        <Layers className="h-3.5 w-3.5 flex-shrink-0" />
        <span>{modeLabel}</span>
        {costStatus && costStatus !== 'unknown' && (
          <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-[10px]">{costStatus}</span>
        )}
      </div>

      {taskSummaries.length > 0 && (
        <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
          {taskSummaries.map((task, idx) => (
            <div key={idx} className="rounded-lg border p-2.5 bg-muted/30">
              <div className="font-mono text-xs text-primary">{task.agent_type}</div>
              <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{task.objective}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
