'use client';

/**
 * [INPUT] @/services/cron::CronJob (POS: Cron 任务 DTO), @/store/useCronStore::jobs (POS: context_from 引用的上游任务名)
 * [OUTPUT] CronJobMetaBadges: 卡片元信息行（调度、Agent、会话、投递、触发器、上下文、技能、到期、超时、下次/上次运行徽标）
 * [POS] CronJobCard 的只读元信息区块；上次运行的状态着色与相对时间在此计算。
 */

import { memo } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import Link from 'next/link';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import {
  Clock,
  AlertTriangle,
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
  Wrench,
  History,
} from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { cn } from '@/lib/utils/classnameUtils';
import type { CronJob } from '@/services/cron';
import ChannelIcon from '@/components/features/settings/sections/integration/channels/ChannelIcon';
import { formatNextRun, formatRelativeTime, formatTime, formatTimeoutSeconds } from './cron-utils';
import { humanizeSchedule, type ScheduleT } from './cron-blueprints';
import useCronStore from '@/store/useCronStore';
import useChatStore from '@/store/useChatStore';
import useAgentStore from '@/store/useAgentStore';
import { CronWorkflowTemplateBadge } from './CronWorkflowTemplateBinding';

function ScheduleLabel({ job, t, locale }: { job: CronJob; t: ScheduleT; locale: string }) {
  const s = job.schedule;
  if (!s) {
    return null;
  }
  const label = humanizeSchedule(s, t, locale);
  return label ? <span>{label}</span> : null;
}

function AgentLabel({ agentId }: { agentId?: string | null }) {
  const agents = useAgentStore((s) => s.agents);
  const locale = useLocale();
  if (!agentId) {
    return null;
  }
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
  if (!chatId) {
    return null;
  }
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

export const CronJobMetaBadges = memo(({ job }: { job: CronJob }) => {
  const t = useTranslations('cron');
  const tCommon = useTranslations('common');
  const locale = useLocale();
  const allJobs = useCronStore((s) => s.jobs);
  const lastRunColor =
    job.last_status === 'error'
      ? 'text-rose-600 dark:text-rose-400'
      : job.last_status === 'skipped'
        ? 'text-amber-600 dark:text-amber-400'
        : 'text-muted-foreground';

  return (
    <>
      <ScheduleLabel job={job} t={t} locale={locale} />
      <AgentLabel agentId={job.agent_id} />
      <CronWorkflowTemplateBadge job={job} />
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
      {typeof job.max_fires === 'number' && (
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
      {job.skill_ids && job.skill_ids.length > 0 && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-flex items-center gap-0.5 text-indigo-600 dark:text-indigo-400">
              <Wrench className="h-3 w-3" />
              <span>{job.skill_ids.length === 1 ? job.skill_ids[0] : `${job.skill_ids.length} skills`}</span>
            </span>
          </TooltipTrigger>
          <TooltipContent>{job.skill_ids.join(', ')}</TooltipContent>
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
            {t('expiresAtLabel')}: {formatTime(job.expires_at, locale)}
          </TooltipContent>
        </Tooltip>
      )}
      {job.timeout_seconds && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-flex items-center gap-0.5">
              <Hourglass className="h-3 w-3" />
              {formatTimeoutSeconds(job.timeout_seconds)}
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
      {job.last_run_at && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className={cn('inline-flex items-center gap-0.5 cursor-default', lastRunColor)}>
              <History className="h-3 w-3" />
              {t('lastRunLabel')}: {formatRelativeTime(job.last_run_at, tCommon, locale)}
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {job.last_status && job.last_status !== 'ok' && (
              <span className="mr-1 font-medium">
                {t(job.last_status === 'error' ? 'runError' : 'runSkipped')}
                {' · '}
              </span>
            )}
            {t('lastRunTooltip', { time: formatTime(job.last_run_at, locale) })}
          </TooltipContent>
        </Tooltip>
      )}
    </>
  );
});
CronJobMetaBadges.displayName = 'CronJobMetaBadges';
