/**
 * [INPUT]
 * - services/agent::AgentListItem
 * - services/agent::AgentFleetStats
 * - next-intl::useTranslations
 * - next/link
 *
 * [OUTPUT]
 * - AgentCard: Agent item card for agents overview list
 *
 * [POS]
 * Extracted from app/agents/page.tsx to keep page under 400 lines limit.
 */

'use client';

import React from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { AgentAvatar } from '@/components/agent/AgentAvatar';
import { Button } from '@/components/primitives/button';
import { agentSettingsHref } from '@/components/features/loadout/loadoutDeepLinks';
import { getBuiltinAgentName, getBuiltinAgentDescription } from '@/components/agent/builtin-agent-i18n';
import type { AgentListItem, AgentFleetStats } from '@/services/agent';
import {
  Settings,
  Trash2,
  MessageSquare,
  Clock,
  ShieldAlert,
  Coins,
  Zap,
  Layers,
} from 'lucide-react';

interface AgentCardProps {
  agent: AgentListItem;
  stats: AgentFleetStats | undefined;
  locale: string;
  t: ReturnType<typeof useTranslations>;
  onEdit: (agent: AgentListItem) => void;
  onDelete: (id: string) => void;
}

function formatTokens(count: number): string {
  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(1)}M`;
  }
  if (count >= 1_000) {
    return `${(count / 1_000).toFixed(1)}K`;
  }
  return String(count);
}

function formatCost(usd: number): string {
  if (usd >= 100) {
    return `$${usd.toFixed(0)}`;
  }
  if (usd >= 1) {
    return `$${usd.toFixed(2)}`;
  }
  return `$${usd.toFixed(3)}`;
}

function StatusDot({ status }: { status: 'busy' | 'idle' }) {
  if (status === 'busy') {
    return (
      <span className="relative flex h-2.5 w-2.5">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-500" />
      </span>
    );
  }
  return <span className="inline-flex rounded-full h-2.5 w-2.5 bg-muted-foreground/30" />;
}

export function AgentCard({
  agent,
  stats,
  locale,
  t,
  onEdit,
  onDelete,
}: AgentCardProps) {
  const tLoadout = useTranslations('loadout');
  const status = stats?.status ?? 'idle';

  return (
    <div className="rounded-xl border bg-card text-card-foreground shadow-xs transition-all hover:shadow-md overflow-hidden flex flex-col">
      <div className="p-6 flex-1">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <AgentAvatar url={agent.avatar_url} name={agent.name} agentId={agent.id} size="lg" />
            <StatusDot status={status} />
          </div>
          <div className="flex items-center gap-1.5">
            {agent.is_built_in && (
              <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold border-transparent bg-secondary text-secondary-foreground">
                {t('builtin', { fallback: 'Built-in' })}
              </span>
            )}
          </div>
        </div>
        <h3 className="text-lg font-semibold mt-4">{getBuiltinAgentName(agent.id, agent.name, locale)}</h3>
        <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
          {getBuiltinAgentDescription(agent.id, agent.description || '', locale) ||
            t('noDescription', { fallback: 'No description provided.' })}
        </p>

        {stats && (stats.monthTokens > 0 || stats.cronCount > 0 || stats.pendingApprovals > 0) && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-3 text-xs text-muted-foreground">
            {stats.monthTokens > 0 && (
              <span className="flex items-center gap-1" title={`${stats.monthTokens.toLocaleString()} tokens`}>
                <Zap className="h-3 w-3" />
                {formatTokens(stats.monthTokens)}
              </span>
            )}
            {stats.monthCost > 0 && (
              <span className="flex items-center gap-1">
                <Coins className="h-3 w-3" />
                {formatCost(stats.monthCost)}
              </span>
            )}
            {stats.sessionCount > 0 && (
              <span className="flex items-center gap-1">
                <MessageSquare className="h-3 w-3" />
                {stats.sessionCount}
              </span>
            )}
            {stats.cronCount > 0 && (
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {stats.cronCount}
              </span>
            )}
            {stats.pendingApprovals > 0 && (
              <span className="flex items-center gap-1 text-orange-500">
                <ShieldAlert className="h-3 w-3" />
                {stats.pendingApprovals}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="bg-muted/50 p-4 flex items-center justify-end gap-2 border-t">
        <Button asChild variant="outline" size="sm" className="h-8">
          <Link href={agentSettingsHref(agent.id)}>
            <Layers className="mr-2 h-4 w-4" />
            {tLoadout('openLoadout')}
          </Link>
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-8"
          onClick={() => window.open(`/?agent_id=${agent.id}`, '_blank', 'noopener,noreferrer')}
        >
          <MessageSquare className="mr-2 h-4 w-4" />
          {t('testChat', { fallback: 'Test Chat' })}
        </Button>
        <Button variant="ghost" size="sm" className="h-8" onClick={() => onEdit(agent)}>
          <Settings className="mr-2 h-4 w-4" />
          {t('settings', { fallback: 'Settings' })}
        </Button>
        {!agent.is_built_in && (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 text-destructive hover:text-destructive"
            onClick={() => onDelete(agent.id)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  );
}
