'use client';

import { memo, useCallback, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useTranslations, useLocale } from 'next-intl';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import {
  Timer,
  Terminal,
  FileCode2,
  Clock,
  Pause,
  Play,
  Trash2,
  RotateCw,
  Copy,
  AlertTriangle,
  Cpu,
  Hourglass,
  Webhook,
  SunMoon,
  BarChart3,
  Hash,
  Bell,
  Bot,
  CalendarClock,
  Zap,
  Link2,
  MessageCircle,
} from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from 'sonner';
import type { CronJob } from '@/services/cron';
import ChannelIcon from '@/components/features/settings/sections/integration/channels/ChannelIcon';
import { updateCronJob, duplicateCronJob } from '@/services/cron';
import { formatNextRun, statusBorderColor, STATUS_BADGE_STYLE, STATUS_DOT_COLOR } from './cron-utils';
import useCronStore from '@/store/useCronStore';
import useChatStore from '@/store/useChatStore';
import useAgentStore from '@/store/useAgentStore';
import useProviderStore from '@/store/useProviderStore';
import { useShallow } from 'zustand/react/shallow';
import { getLiteLLMModelName } from '@/store/config/providerTypes';
import ModelPickerPopover from '@/components/features/app-shell/model-picker-popover';

interface CronJobCardProps {
  job: CronJob;
  onSelect: (job: CronJob) => void;
  onRequestDelete: (job: CronJob) => void;
}

function parseLiteLLM(model: string): { providerId: string; model: string } {
  const idx = model.indexOf('/');
  if (idx > 0) return { providerId: model.slice(0, idx), model: model.slice(idx + 1) };
  return { providerId: 'openai', model };
}

function ScheduleLabel({ job, t }: { job: CronJob; t: (key: string, values?: Record<string, string>) => string }) {
  const s = job.schedule;
  if (s.kind === 'cron') return <span className="font-mono">{s.expr}</span>;
  if (s.kind === 'interval' && s.interval_ms) {
    const sec = Math.round(s.interval_ms / 1000);
    const label =
      sec < 60 ? t('timeSeconds', { value: String(sec) }) : t('timeMinutes', { value: String(Math.round(sec / 60)) });
    return <span>{t('interval', { value: label })}</span>;
  }
  if (s.kind === 'once') return <span>{t('once')}</span>;
  return null;
}

function AgentLabel({ agentId }: { agentId?: string | null }) {
  const agents = useAgentStore((s) => s.agents);
  const locale = useLocale();
  if (!agentId) return null;
  const agent = agents.find((a) => a.id === agentId);
  const name = agent ? getBuiltinAgentName(agent.id, agent.name, locale) : agentId;
  return (
    <span className="inline-flex items-center gap-0.5 text-indigo-600 dark:text-indigo-400">
      <Bot className="h-3 w-3" />
      <span className="truncate max-w-[100px]">{name}</span>
    </span>
  );
}

function ThreadBadge({ chatId, t }: { chatId?: string; t: (key: string) => string }) {
  const chatHistoryItems = useChatStore((s) => s.chatHistoryItems);
  if (!chatId) return null;
  const chat = chatHistoryItems.find((c) => c.id === chatId);
  const label = chat?.title || chatId.slice(0, 8);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link href={`/${chatId}`} onClick={(e) => e.stopPropagation()}>
          <span className="inline-flex items-center gap-0.5 text-sky-600 dark:text-sky-400 hover:underline">
            <MessageCircle className="h-3 w-3" />
            <span className="truncate max-w-[100px]">{label}</span>
          </span>
        </Link>
      </TooltipTrigger>
      <TooltipContent>{t('threadAutomationTooltip')}</TooltipContent>
    </Tooltip>
  );
}

const CronJobCard = memo<CronJobCardProps>(({ job, onSelect, onRequestDelete }) => {
  const t = useTranslations('cron');
  const { pauseJob, resumeJob, triggerJob, fetchJobs, jobs: allJobs } = useCronStore();
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
  const TypeIcon =
    job.job_type === 'shell' ? Terminal : isScriptJob ? FileCode2 : isReminderJob ? Clock : Timer;

  const canResume = useMemo(() => {
    if (job.status === 'active') return true;
    if (job.status === 'completed') return false;
    if (job.expires_at && new Date(job.expires_at).getTime() <= Date.now()) return false;
    if (job.max_fires != null && job.fire_count >= job.max_fires) return false;
    return true;
  }, [job.status, job.expires_at, job.max_fires, job.fire_count]);

  const handleToggle = useCallback(async () => {
    try {
      if (job.status === 'active') {
        await pauseJob(job.id);
        toast.success(t('pauseSuccess', { name: job.name }));
      } else {
        await resumeJob(job.id);
        toast.success(t('resumeSuccess', { name: job.name }));
      }
    } catch {
      toast.error(t('actionFail'));
    }
  }, [job, pauseJob, resumeJob, t]);

  const [triggering, setTriggering] = useState(false);

  const handleTrigger = useCallback(async () => {
    if (triggering) return;
    setTriggering(true);
    try {
      await triggerJob(job.id);
      toast.success(t('triggerSuccess', { name: job.name }));
    } catch {
      toast.error(t('triggerFail'));
      setTriggering(false);
      return;
    }
    setTimeout(() => setTriggering(false), 5_000);
  }, [triggering, job, triggerJob, t]);

  const [duplicating, setDuplicating] = useState(false);

  const handleDuplicate = useCallback(async () => {
    if (duplicating) return;
    setDuplicating(true);
    try {
      await duplicateCronJob(job.id);
      toast.success(t('duplicateSuccess', { name: job.name }));
      fetchJobs(true);
    } catch {
      toast.error(t('duplicateFail'));
    } finally {
      setDuplicating(false);
    }
  }, [duplicating, job, fetchJobs, t]);

  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-lg border border-l-[3px] bg-card px-3 py-2.5',
        'hover:bg-accent/40 cursor-pointer transition-colors',
        statusBorderColor(job),
      )}
      onClick={() => {
        if (!suppressNavRef.current) onSelect(job);
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
          <ScheduleLabel job={job} t={t} />
          <AgentLabel agentId={job.agent_id} />
          {job.session_target === 'main' && <ThreadBadge chatId={job.chat_id} t={t} />}
          {job.delivery?.channel && job.delivery.channel !== 'chat' && job.delivery.channel !== 'none' && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-0.5 text-blue-600 dark:text-blue-400">
                  {job.delivery.channel === 'webhook' ? (
                    <Webhook className="h-3 w-3" />
                  ) : (
                    <ChannelIcon channelId={job.delivery.channel} size={12} />
                  )}
                  <span className="truncate max-w-[80px]">{job.delivery.channel}</span>
                </span>
              </TooltipTrigger>
              <TooltipContent>{job.delivery.target ?? job.delivery.channel}</TooltipContent>
            </Tooltip>
          )}
          {job.failure_delivery && job.failure_delivery.channel !== 'chat' && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-0.5 text-rose-600 dark:text-rose-400">
                  <AlertTriangle className="h-3 w-3" />
                  <span className="truncate max-w-[80px]">{t('failureDeliveryTag')}</span>
                </span>
              </TooltipTrigger>
              <TooltipContent>{t('failureDeliveryTooltip', { channel: job.failure_delivery.channel })}</TooltipContent>
            </Tooltip>
          )}
          {job.active_hours && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-0.5 text-violet-600 dark:text-violet-400">
                  <SunMoon className="h-3 w-3" />
                  <span>
                    {job.active_hours.start}–{job.active_hours.end}
                  </span>
                </span>
              </TooltipTrigger>
              <TooltipContent>
                {t('activeHoursTooltip', {
                  start: job.active_hours.start,
                  end: job.active_hours.end,
                  tz: job.active_hours.tz,
                })}
              </TooltipContent>
            </Tooltip>
          )}
          {job.monitor_config?.enabled && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-0.5 text-emerald-600 dark:text-emerald-400">
                  <BarChart3 className="h-3 w-3" />
                  <span>{t('incrementalMonitorBadge')}</span>
                </span>
              </TooltipTrigger>
              <TooltipContent>
                {t('incrementalMonitorTooltip', { ttl: String(job.monitor_config.ttl_days) })}
              </TooltipContent>
            </Tooltip>
          )}
          {job.max_fires != null && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-0.5 text-orange-600 dark:text-orange-400">
                  <Hash className="h-3 w-3" />
                  <span>
                    {t('fireCountValue', {
                      count: String(job.fire_count),
                      max: String(job.max_fires),
                    })}
                  </span>
                </span>
              </TooltipTrigger>
              <TooltipContent>{t('maxFiresLabel')}</TooltipContent>
            </Tooltip>
          )}
          {typeof job.failure_alert === 'object' && job.failure_alert?.enabled && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-0.5 text-rose-600 dark:text-rose-400">
                  <Bell className="h-3 w-3" />
                </span>
              </TooltipTrigger>
              <TooltipContent>{t('failureAlertLabel')}</TooltipContent>
            </Tooltip>
          )}
          {job.triggers &&
            (job.triggers.webhooks.length > 0 ||
              job.triggers.events.length > 0 ||
              job.triggers.system_events.length > 0) && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="inline-flex items-center gap-0.5 text-cyan-600 dark:text-cyan-400">
                    <Zap className="h-3 w-3" />
                    <span>{t('triggersLabel')}</span>
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  {[
                    job.triggers.webhooks.length > 0 && `${job.triggers.webhooks.length} webhook`,
                    job.triggers.events.length > 0 && `${job.triggers.events.length} event`,
                    job.triggers.system_events.length > 0 && `${job.triggers.system_events.length} system`,
                  ]
                    .filter(Boolean)
                    .join(', ')}
                </TooltipContent>
              </Tooltip>
            )}
          {job.context_from?.length > 0 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-0.5 text-teal-600 dark:text-teal-400">
                  <Link2 className="h-3 w-3" />
                  <span>{t('contextFromBadge', { count: String(job.context_from.length) })}</span>
                </span>
              </TooltipTrigger>
              <TooltipContent>
                {t('contextFromTooltip', {
                  ids: job.context_from.map((id) => allJobs.find((j) => j.id === id)?.name ?? id).join(', '),
                })}
              </TooltipContent>
            </Tooltip>
          )}
          {job.expires_at && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-0.5 text-amber-600 dark:text-amber-400">
                  <CalendarClock className="h-3 w-3" />
                </span>
              </TooltipTrigger>
              <TooltipContent>
                {t('expiresAtLabel')}: {new Date(job.expires_at).toLocaleString()}
              </TooltipContent>
            </Tooltip>
          )}
          {job.timeout_seconds && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-0.5">
                  <Hourglass className="h-3 w-3" />
                  {job.timeout_seconds >= 60 ? `${Math.round(job.timeout_seconds / 60)}m` : `${job.timeout_seconds}s`}
                </span>
              </TooltipTrigger>
              <TooltipContent>{t('timeoutLabel')}</TooltipContent>
            </Tooltip>
          )}
          {job.next_run_at && (
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatNextRun(job.next_run_at, t)}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-0.5 shrink-0" onClick={(e) => e.stopPropagation()}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7"
              onClick={handleTrigger}
              disabled={job.status !== 'active' || triggering}
            >
              <RotateCw className={cn('h-3.5 w-3.5', triggering && 'animate-spin')} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t('trigger')}</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={handleDuplicate} disabled={duplicating}>
              <Copy className="h-3.5 w-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t('duplicate')}</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7"
              onClick={handleToggle}
              disabled={job.status !== 'active' && !canResume}
            >
              {job.status === 'active' ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {job.status === 'active'
              ? t('pause')
              : canResume
                ? t('resume')
                : t('resumeBlocked')}
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7 text-destructive hover:text-destructive"
              onClick={() => onRequestDelete(job)}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t('delete')}</TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
});

CronJobCard.displayName = 'CronJobCard';
export default CronJobCard;
