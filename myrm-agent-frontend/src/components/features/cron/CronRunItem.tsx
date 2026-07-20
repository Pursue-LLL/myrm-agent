'use client';

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronDown, ChevronUp, Cpu, Send, CircleX, Coins, ShieldAlert, ShieldCheck, Zap, Wrench } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { CronRun } from '@/services/cron';
import { formatDuration, formatTime } from './cron-utils';

interface CronRunItemProps {
  run: CronRun;
  isLast: boolean;
  showJobName?: boolean;
}

function formatTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

const SECURITY_DENIAL_PATTERNS = [
  'cron fail-closed policy',
  'denied by security policy',
  'Tool execution denied',
] as const;

function hasSecurityDenial(run: CronRun): boolean {
  const text = `${run.output ?? ''} ${run.error ?? ''}`;
  return SECURITY_DENIAL_PATTERNS.some((p) => text.includes(p));
}

const CronRunItem = memo<CronRunItemProps>(({ run, isLast, showJobName }) => {
  const t = useTranslations('cron');
  const [expanded, setExpanded] = useState(false);
  const isOk = run.status === 'ok';
  const isSkipped = run.status === 'skipped';
  const hasContent = !!(run.output || run.error);
  const securityDenied = !isOk && !isSkipped && hasSecurityDenial(run);
  const verification = run.metadata?.verification;
  const monitorContractError = run.metadata?.monitor_contract_error;
  const monitorContractErrorLabel =
    monitorContractError === 'invalid_json_like_output'
      ? t('monitorContractErrorInvalidJson')
      : monitorContractError
        ? t('monitorContractErrorGeneric')
        : null;
  const verificationLabel =
    verification?.status === 'pass'
      ? t('verificationPass')
      : verification?.status === 'fail'
        ? t('verificationFail')
        : verification?.status === 'skipped'
          ? t('verificationSkipped')
          : verification?.status === 'error'
            ? t('verificationError')
            : null;

  const deliveryLabel =
    run.delivery_status === 'delivered'
      ? t('deliveryDelivered')
      : run.delivery_status === 'failed'
        ? t('deliveryFailed')
        : run.delivery_status === 'skipped'
          ? t('deliverySkipped')
          : null;

  const deliveryIcon =
    run.delivery_status === 'delivered' ? (
      <Send className="h-3 w-3 text-green-500" />
    ) : run.delivery_status === 'failed' ? (
      <CircleX className="h-3 w-3 text-destructive" />
    ) : null;

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center shrink-0 w-4">
        <div
          className={cn(
            'h-3 w-3 rounded-full border-2 shrink-0',
            isOk
              ? 'border-green-500 bg-green-500/20'
              : isSkipped
                ? 'border-amber-500 bg-amber-500/20'
                : 'border-destructive bg-destructive/20',
          )}
        />
        {!isLast && <div className="flex-1 w-px bg-border mt-1" />}
      </div>

      <div className={cn('flex-1 min-w-0 pb-4', isLast && 'pb-0')}>
        <div className="flex items-center gap-1.5 flex-wrap">
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium leading-tight',
              isOk
                ? 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20'
                : isSkipped
                  ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
                  : 'bg-destructive/10 text-destructive border-destructive/20',
            )}
          >
            <span
              className={cn(
                'h-1.5 w-1.5 rounded-full',
                isOk ? 'bg-green-500' : isSkipped ? 'bg-amber-500' : 'bg-destructive',
              )}
            />
            {isOk ? t('runOk') : isSkipped ? t('runSkipped') : t('runError')}
          </span>

          {showJobName && run.job_name && (
            <span className="text-xs font-medium text-foreground truncate max-w-[120px]">{run.job_name}</span>
          )}

          {run.trigger_source && run.trigger_source !== 'cron' && (
            <span className="inline-flex items-center gap-0.5 text-[10px] text-cyan-600 dark:text-cyan-400 bg-cyan-500/10 rounded px-1 py-0.5">
              <Zap className="h-2.5 w-2.5" />
              {run.trigger_source}
            </span>
          )}

          {run.model && (
            <span className="inline-flex items-center gap-0.5 text-[10px] text-muted-foreground bg-muted rounded px-1 py-0.5">
              <Cpu className="h-2.5 w-2.5" />
              {run.model.split('/').pop()}
            </span>
          )}

          {deliveryIcon && (
            <span
              className="inline-flex items-center gap-0.5"
              title={run.delivery_error ?? deliveryLabel ?? run.delivery_status}
            >
              {deliveryIcon}
              {run.delivery_status === 'failed' && (
                <span className="text-[10px] text-destructive">{deliveryLabel}</span>
              )}
            </span>
          )}

          {securityDenied && (
            <span
              className="inline-flex items-center gap-0.5 text-[10px] text-amber-600 dark:text-amber-400"
              title={t('securityDenied')}
            >
              <ShieldAlert className="h-3 w-3" />
              {t('securityDenied')}
            </span>
          )}

          {monitorContractErrorLabel && (
            <span
              className="inline-flex items-center gap-0.5 text-[10px] text-amber-600 dark:text-amber-400"
              title={monitorContractErrorLabel}
            >
              <ShieldAlert className="h-3 w-3" />
              {t('monitorContractError')}
            </span>
          )}

          {verificationLabel && (
            <span
              className={cn(
                'inline-flex items-center gap-0.5 text-[10px] rounded px-1 py-0.5',
                verification?.status === 'pass'
                  ? 'text-green-600 dark:text-green-400 bg-green-500/10'
                  : verification?.status === 'fail'
                    ? 'text-destructive bg-destructive/10'
                    : 'text-muted-foreground bg-muted',
              )}
              title={verification?.summary ?? verificationLabel}
            >
              <ShieldCheck className="h-3 w-3" />
              {verificationLabel}
            </span>
          )}

          <span className="text-xs text-muted-foreground">{formatDuration(run.duration_ms)}</span>
          <span className="text-xs text-muted-foreground">{formatTime(run.started_at)}</span>

          {run.usage_total_tokens != null && run.usage_total_tokens > 0 && (
            <span className="inline-flex items-center gap-0.5 text-[10px] text-muted-foreground">
              <Coins className="h-2.5 w-2.5" />
              {formatTokens(run.usage_total_tokens)}
            </span>
          )}

          {hasContent && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-0.5 ml-auto"
            >
              {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              {!expanded && t('viewOutput')}
            </button>
          )}
        </div>

        {!expanded && run.output && (
          <p className="text-xs text-muted-foreground mt-1 line-clamp-1 font-mono">{run.output}</p>
        )}
        {!expanded && verification?.status === 'fail' && isOk && (
          <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-1">{t('verificationRunOkReviewFailed')}</p>
        )}
        {!expanded && monitorContractErrorLabel && (
          <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-1">{monitorContractErrorLabel}</p>
        )}
        {!expanded && !run.output && run.error && (
          <p className="text-xs text-destructive mt-1 line-clamp-1">{run.error}</p>
        )}

        {expanded && (
          <div className="mt-2 space-y-1.5">
            {run.usage_input_tokens != null && (
              <div className="flex gap-3 text-[10px] text-muted-foreground">
                <span>Input: {formatTokens(run.usage_input_tokens)}</span>
                {run.usage_output_tokens != null && <span>Output: {formatTokens(run.usage_output_tokens)}</span>}
              </div>
            )}
            {run.metadata?.progressSteps && Array.isArray(run.metadata.progressSteps) && run.metadata.progressSteps.length > 0 && (
              <div className="rounded-lg border border-border/40 bg-muted/20 p-2 space-y-1">
                <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                  <Wrench className="h-3 w-3" />
                  {t('executionSteps')} ({run.metadata.progressSteps.length})
                </p>
                <div className="space-y-0.5">
                  {run.metadata.progressSteps.map((step, idx) => (
                    <div key={idx} className="flex items-center gap-1.5 text-[10px]">
                      <span
                        className={cn(
                          'h-1.5 w-1.5 rounded-full shrink-0',
                          step.error ? 'bg-red-400' : 'bg-emerald-400',
                        )}
                      />
                      <span className="font-mono text-foreground/80 truncate">
                        {step.tool_name || step.step_key || `step ${idx + 1}`}
                      </span>
                      {step.error && (
                        <span className="text-red-400 truncate ml-1" title={step.error}>
                          {step.error}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {run.output && (
              <pre className="text-xs text-muted-foreground bg-muted/50 rounded-lg p-2 overflow-x-auto whitespace-pre-wrap break-words font-mono max-h-60 overflow-y-auto">
                {run.output}
              </pre>
            )}
            {run.error && (
              <pre className="text-xs text-destructive bg-destructive/5 rounded-lg p-2 overflow-x-auto whitespace-pre-wrap break-words max-h-40 overflow-y-auto">
                {run.error}
              </pre>
            )}
            {run.delivery_error && (
              <p className="text-[10px] text-destructive">
                {t('deliveryError')}: {run.delivery_error}
              </p>
            )}
            {securityDenied && (
              <div className="flex items-start gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/5 px-2.5 py-1.5">
                <ShieldAlert className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
                <p className="text-[11px] text-amber-700 dark:text-amber-300">{t('securityDeniedHint')}</p>
              </div>
            )}
            {monitorContractErrorLabel && (
              <div className="flex items-start gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/5 px-2.5 py-1.5">
                <ShieldAlert className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
                <div className="space-y-0.5">
                  <p className="text-[11px] font-medium text-amber-700 dark:text-amber-300">
                    {t('monitorContractError')}
                  </p>
                  <p className="text-[11px] text-amber-700 dark:text-amber-300">{monitorContractErrorLabel}</p>
                </div>
              </div>
            )}
            {verification && (
              <div
                className={cn(
                  'rounded-lg border px-2.5 py-2 space-y-1',
                  verification.status === 'pass'
                    ? 'border-green-500/30 bg-green-500/5'
                    : verification.status === 'fail'
                      ? 'border-destructive/30 bg-destructive/5'
                      : 'border-border/40 bg-muted/30',
                )}
              >
                <p className="text-[11px] font-medium text-foreground">{t('verificationSummary')}</p>
                <p className="text-[11px] text-muted-foreground">{verificationLabel}</p>
                {verification.summary && (
                  <p className="text-[11px] text-muted-foreground whitespace-pre-wrap break-words">{verification.summary}</p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
});

CronRunItem.displayName = 'CronRunItem';
export default CronRunItem;
