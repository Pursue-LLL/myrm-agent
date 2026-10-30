'use client';

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Check, Copy, Wrench } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils/classnameUtils';
import type { CronRun } from '@/services/cron';

interface CronRunStepsProps {
  run: CronRun;
}

/** The steps an agent run took, with a button that copies the run's whole audit trace as JSON. */
const CronRunSteps = memo<CronRunStepsProps>(({ run }) => {
  const t = useTranslations('cron');
  const [copied, setCopied] = useState(false);
  const steps = run.metadata?.progressSteps;

  if (!Array.isArray(steps) || steps.length === 0) {
    return null;
  }

  const handleCopyAuditTrace = () => {
    const traceData = {
      run_id: run.id,
      job_id: run.job_id,
      status: run.status,
      started_at: run.started_at,
      duration_ms: run.duration_ms,
      trigger_source: run.trigger_source || 'cron',
      model: run.model,
      usage: {
        input: run.usage_input_tokens,
        output: run.usage_output_tokens,
        total: run.usage_total_tokens,
      },
      steps,
      verification: run.metadata?.verification,
      output: run.output,
      error: run.error,
    };
    void navigator.clipboard.writeText(JSON.stringify(traceData, null, 2));
    setCopied(true);
    toast.success(t('traceCopied'));
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="rounded-lg border border-border/40 bg-muted/20 p-2 space-y-1.5">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1">
          <Wrench className="h-3 w-3" />
          {t('executionSteps')} ({steps.length})
        </p>
        <button
          type="button"
          onClick={handleCopyAuditTrace}
          className="text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-1 bg-background/50 border border-border/50 rounded px-1.5 py-0.5"
        >
          {copied ? <Check className="h-2.5 w-2.5 text-green-500" /> : <Copy className="h-2.5 w-2.5" />}
          {t('copyAuditTrace')}
        </button>
      </div>
      <div className="space-y-1">
        {steps.map((step, idx) => (
          <div key={idx} className="flex items-center gap-1.5 text-[10px] bg-background/30 rounded px-1.5 py-1">
            <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', step.error ? 'bg-red-400' : 'bg-emerald-400')} />
            <span className="font-mono font-medium text-foreground/90 truncate">
              {step.tool_name || step.step_key || t('stepFallback', { index: idx + 1 })}
            </span>
            {step.error && (
              <span className="text-rose-700 dark:text-rose-400 truncate ml-auto" title={step.error}>
                {step.error}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
});

CronRunSteps.displayName = 'CronRunSteps';
export default CronRunSteps;
