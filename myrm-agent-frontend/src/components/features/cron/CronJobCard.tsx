'use client';

import { memo, useCallback, useMemo, useRef } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { Timer, Terminal, FileCode2, Clock, AlertTriangle, Cpu } from 'lucide-react';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from 'sonner';
import type { CronJob } from '@/services/cron';
import { updateCronJob } from '@/services/cron';
import { formatTime, isCronOverdue, statusBorderColor, STATUS_BADGE_STYLE, STATUS_DOT_COLOR } from './cron-utils';
import useCronStore from '@/store/useCronStore';
import useProviderStore from '@/store/useProviderStore';
import { useShallow } from 'zustand/react/shallow';
import { getLiteLLMModelName } from '@/store/config/providerTypes';
import ModelPickerPopover from '@/components/features/app-shell/model-picker-popover';
import { CronJobMetaBadges } from './CronJobCardMeta';
import { CronJobCardActions } from './CronJobCardActions';
import { useCronJobActions } from './useCronJobActions';
import { useDeployMode } from '@/hooks/shared/useDeployMode';

interface CronJobCardProps {
  job: CronJob;
  onSelect: (job: CronJob) => void;
  onRequestDelete: (job: CronJob) => void;
}

function parseLiteLLM(model: string): { providerId: string; model: string } {
  const idx = model.indexOf('/');
  if (idx > 0) {
    return { providerId: model.slice(0, idx), model: model.slice(idx + 1) };
  }
  return { providerId: 'openai', model };
}

const CronJobCard = memo<CronJobCardProps>(({ job, onSelect, onRequestDelete }) => {
  const t = useTranslations('cron');
  const locale = useLocale();
  const deployMode = useDeployMode();
  const isCloud = deployMode.isSandbox && !deployMode.isLocal && !deployMode.isLoading;
  const overdue = isCronOverdue(job);
  const overdueTime = overdue && job.next_run_at ? formatTime(job.next_run_at, locale) : null;
  const fetchJobs = useCronStore((s) => s.fetchJobs);
  const { providers, defaultModelConfig } = useProviderStore(
    useShallow((s) => ({
      providers: s.providers,
      defaultModelConfig: s.defaultModelConfig,
    })),
  );

  const { displayModelName, currentSelection } = useMemo(() => {
    if (job.model) {
      const parsed = parseLiteLLM(job.model);
      return { displayModelName: parsed.model, currentSelection: parsed };
    }
    const sel = defaultModelConfig.baseModel.primary;
    return {
      displayModelName: sel?.model || t('noModel'),
      currentSelection: sel ? { providerId: sel.providerId, model: sel.model } : null,
    };
  }, [job.model, defaultModelConfig, t]);

  const suppressNavRef = useRef(false);

  const handleModelChange = useCallback(
    async (providerId: string, model: string) => {
      suppressNavRef.current = true;
      setTimeout(() => {
        suppressNavRef.current = false;
      }, 300);
      const prov = providers.find((p) => p.id === providerId);
      const liteName = getLiteLLMModelName(providerId, model, prov?.providerType);
      try {
        await updateCronJob(job.id, { model: liteName });
        fetchJobs(true);
      } catch {
        toast.error(t('actionFail'));
      }
    },
    [job.id, providers, fetchJobs, t],
  );

  const statusLabel: Record<string, string> = {
    active: t('statusActive'),
    paused: t('statusPaused'),
    completed: t('statusCompleted'),
  };
  const isScriptJob = job.job_type === 'router' && !!job.pre_condition_script && !job.prompt;
  const isReminderJob = job.job_type === 'reminder';
  const TypeIcon = job.job_type === 'shell' ? Terminal : isScriptJob ? FileCode2 : isReminderJob ? Clock : Timer;

  const { canResume, triggering, duplicating, handleToggle, handleTrigger, handleDuplicate } = useCronJobActions(job);

  return (
    // Card is clickable but contains nested action buttons, so a real <button>
    // wrapper is invalid HTML; role="button" is the accessible equivalent.
    /* oxlint-disable jsx-a11y/prefer-tag-over-role -- clickable card with nested action buttons */
    <div
      role="button"
      tabIndex={0}
      className={cn(
        'flex items-start gap-3 rounded-lg border border-l-[3px] bg-card px-3 py-2.5',
        'hover:bg-accent/40 cursor-pointer transition-colors',
        statusBorderColor(job),
      )}
      onClick={() => {
        if (!suppressNavRef.current) {
          onSelect(job);
        }
      }}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && !suppressNavRef.current) {
          e.preventDefault();
          onSelect(job);
        }
      }}
    >
      <div className="mt-0.5 shrink-0">
        <TypeIcon className="h-4 w-4 text-muted-foreground" />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium truncate">{job.name}</span>
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium leading-tight',
              STATUS_BADGE_STYLE[job.status] ?? 'bg-muted text-muted-foreground border-muted',
            )}
          >
            <span
              className={cn('h-1.5 w-1.5 rounded-full', STATUS_DOT_COLOR[job.status] ?? 'bg-muted-foreground/50')}
            />
            {statusLabel[job.status] ?? job.status}
          </span>
          {job.consecutive_failures > 0 && (
            <Badge
              variant="outline"
              className="text-[10px] leading-tight gap-0.5 text-amber-600 dark:text-amber-400 border-amber-500/30"
            >
              <AlertTriangle className="h-2.5 w-2.5" />
              {t('consecutiveFailures', { value: String(job.consecutive_failures) })}
            </Badge>
          )}
        </div>

        {overdue && overdueTime && (
          <div className="mt-1.5 flex items-start gap-1.5 rounded-md border border-amber-500/25 bg-amber-500/5 px-2 py-1.5 text-[11px] leading-snug text-amber-700 dark:text-amber-300">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
            <span>
              {isCloud
                ? t('overdueBannerCloud', { time: overdueTime })
                : t('overdueBannerLocal', { time: overdueTime })}
            </span>
          </div>
        )}

        {job.prompt && <p className="text-xs text-muted-foreground mt-0.5 truncate">{job.prompt}</p>}

        <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground flex-wrap">
          {!isScriptJob && job.job_type !== 'shell' && job.job_type !== 'reminder' && (
            <ModelPickerPopover
              trigger={
                <button
                  className="flex items-center gap-1 rounded-full border border-transparent px-1.5 py-0.5 -ml-1 text-muted-foreground hover:text-foreground hover:border-border hover:bg-accent/50 transition-all cursor-pointer"
                  onClick={(e) => e.stopPropagation()}
                >
                  <Cpu className="h-3 w-3" />
                  <span className="truncate max-w-[120px]">{displayModelName}</span>
                </button>
              }
              currentSelection={currentSelection}
              onSelect={handleModelChange}
            />
          )}
          <CronJobMetaBadges job={job} />
        </div>
      </div>

      <CronJobCardActions
        job={job}
        triggering={triggering}
        duplicating={duplicating}
        canResume={canResume}
        onTrigger={handleTrigger}
        onDuplicate={handleDuplicate}
        onToggle={handleToggle}
        onRequestDelete={onRequestDelete}
      />
    </div>
  );
});

CronJobCard.displayName = 'CronJobCard';
export default CronJobCard;
