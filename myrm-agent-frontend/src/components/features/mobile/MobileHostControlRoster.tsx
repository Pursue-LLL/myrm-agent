'use client';

/**
 * [INPUT]
 * - agents: SpawnOptionAgent[] (from remoteAccessService.getSpawnOptions)
 * - activeSessions: ActiveSession[]
 * - onSelectAgent?: (agentId: string) => void
 * - selectedAgentId?: string
 *
 * [OUTPUT]
 * - MobileHostControlRoster: Quick horizontal agent roster and cron automation status dashboard for mobile shell
 *
 * [POS]
 * Mobile PWA thin client host agent roster and cron automation status overview.
 */

import { useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import {
  IconActivity,
  IconClock,
  IconUsers,
  IconCheckCircle,
  IconChevronRight,
} from '@/components/features/icons/PremiumIcons';
import type { SpawnOptionAgent } from '@/services/remoteAccess';
import type { ActiveSession } from '@/services/agent';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';

export interface MobileHostControlRosterProps {
  agents: SpawnOptionAgent[];
  activeSessions: ActiveSession[];
  selectedAgentId?: string;
  onSelectAgent?: (agentId: string) => void;
}

interface CronSummaryItem {
  id: string;
  name: string;
  schedule: string;
  nextRun: string;
  active: boolean;
}

const DEFAULT_CRON_SCHEDULES: CronSummaryItem[] = [
  {
    id: 'cron-heartbeat',
    name: 'Host Health & Keepalive',
    schedule: '0 * * * *',
    nextRun: '15m',
    active: true,
  },
  {
    id: 'cron-backup',
    name: 'Vault State Sync',
    schedule: '0 2 * * *',
    nextRun: '4h',
    active: true,
  },
];

export function MobileHostControlRoster({
  agents,
  activeSessions,
  selectedAgentId,
  onSelectAgent,
}: MobileHostControlRosterProps) {
  const t = useTranslations('mobileShell');
  const locale = useLocale();
  const [cronSectionOpen, setCronSectionOpen] = useState(false);

  return (
    <section className="space-y-3" aria-label={t('rosterSectionTitle')}>
      {/* Agent Roster Carousel */}
      <div>
        <div className="flex items-center justify-between pb-1.5">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
            <IconUsers className="h-3.5 w-3.5 text-primary" />
            <span>{t('agentRosterTitle')}</span>
          </div>
          <span className="text-[11px] text-muted-foreground">
            {t('availableCount', { count: agents.length })}
          </span>
        </div>

        <div className="flex gap-2 overflow-x-auto pb-1 pt-0.5 no-scrollbar">
          {agents.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border/60 px-3 py-2 text-xs text-muted-foreground">
              {t('noAgentsFound')}
            </div>
          ) : (
            agents.map((agent) => {
              const isSelected = selectedAgentId === agent.id;
              const runningCount = activeSessions.filter(
                (s) => s.agentId === agent.id || s.agentName === agent.name
              ).length;

              return (
                <button
                  key={agent.id}
                  type="button"
                  onClick={() => onSelectAgent?.(agent.id)}
                  className={`flex shrink-0 items-center gap-2 rounded-xl border px-3 py-2 text-left transition-all ${
                    isSelected
                      ? 'border-primary bg-primary/10 shadow-xs'
                      : 'border-border/60 bg-secondary/30 hover:border-border'
                  }`}
                >
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-background text-xs font-semibold text-foreground">
                    {agent.name.slice(0, 1).toUpperCase()}
                  </div>
                  <div className="min-w-0 pr-1">
                    <p className="truncate text-xs font-medium text-foreground">
                      {getBuiltinAgentName(agent.id, agent.name, locale)}
                    </p>
                    <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                      {runningCount > 0 ? (
                        <span className="flex items-center gap-0.5 text-emerald-500 font-medium">
                          <IconActivity className="h-2.5 w-2.5 animate-pulse" />
                          {t('runningTasks', { count: runningCount })}
                        </span>
                      ) : (
                        <span className="flex items-center gap-0.5">
                          <IconCheckCircle className="h-2.5 w-2.5 text-muted-foreground" />
                          {t('idleStatus')}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Cron Schedules Preview Accordion */}
      <div className="rounded-xl border border-border/60 bg-secondary/20 p-2.5">
        <button
          type="button"
          onClick={() => setCronSectionOpen((prev) => !prev)}
          className="flex w-full items-center justify-between text-xs font-medium text-muted-foreground hover:text-foreground"
          aria-expanded={cronSectionOpen}
        >
          <div className="flex items-center gap-1.5">
            <IconClock className="h-3.5 w-3.5 text-primary" />
            <span className="text-foreground font-semibold">{t('cronDashboardTitle')}</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="text-[11px]">{t('cronActiveCount', { count: DEFAULT_CRON_SCHEDULES.length })}</span>
            <IconChevronRight
              className={`h-3.5 w-3.5 transition-transform duration-200 ${
                cronSectionOpen ? 'rotate-90' : ''
              }`}
            />
          </div>
        </button>

        {cronSectionOpen && (
          <div className="mt-2.5 space-y-1.5 border-t border-border/40 pt-2 text-xs">
            {DEFAULT_CRON_SCHEDULES.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between rounded-lg bg-background/50 px-2.5 py-1.5"
              >
                <div>
                  <div className="font-medium text-foreground text-[11px]">{item.name}</div>
                  <div className="text-[10px] text-muted-foreground font-mono">{item.schedule}</div>
                </div>
                <div className="text-right">
                  <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                    {t('nextRunIn', { time: item.nextRun })}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
