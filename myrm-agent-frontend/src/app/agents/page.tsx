'use client';

import React, { useState, useCallback, useMemo } from 'react';
import useSWR from 'swr';
import { AgentAvatar } from '@/components/agent/AgentAvatar';
import { AgentEditForm } from '@/components/agent/AgentEditForm';
import { Button } from '@/components/primitives/button';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import {
  Plus,
  Settings,
  Trash2,
  MessageSquare,
  Clock,
  ShieldAlert,
  Activity,
  Coins,
  Zap,
} from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import {
  listAgents,
  deleteAgent,
  getFleetOverview,
  AgentListItem,
  AgentFleetStats,
} from '@/services/agent';
import { getBuiltinAgentName, getBuiltinAgentDescription } from '@/components/agent/builtin-agent-i18n';
import { toast } from '@/hooks/useToast';

function formatTokens(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K`;
  return String(count);
}

function formatCost(usd: number): string {
  if (usd >= 100) return `$${usd.toFixed(0)}`;
  if (usd >= 1) return `$${usd.toFixed(2)}`;
  return `$${usd.toFixed(3)}`;
}

export default function AgentsPage() {
  const t = useTranslations('Agent');
  const locale = useLocale();

  const [isEditFormOpen, setIsEditFormOpen] = useState(false);
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null);
  const [deletingAgentId, setDeletingAgentId] = useState<string | null>(null);

  const { data: response, error, isLoading, mutate } = useSWR('listAgents', () => listAgents(1, 100));
  const { data: fleetData } = useSWR('fleetOverview', getFleetOverview, {
    refreshInterval: 5_000,
    revalidateOnFocus: true,
  });

  const agents = response?.items || [];
  const kpi = fleetData?.kpi;
  const agentStatsMap = fleetData?.agents || {};

  const sortedAgents = useMemo(() => {
    if (!agents.length) return agents;
    return [...agents].sort((a, b) => {
      const sa = agentStatsMap[a.id];
      const sb = agentStatsMap[b.id];
      const statusA = sa?.status === 'busy' ? 0 : 1;
      const statusB = sb?.status === 'busy' ? 0 : 1;
      if (statusA !== statusB) return statusA - statusB;
      const costA = sa?.monthCost ?? 0;
      const costB = sb?.monthCost ?? 0;
      return costB - costA;
    });
  }, [agents, agentStatsMap]);

  const handleCreate = () => {
    setEditingAgentId(null);
    setIsEditFormOpen(true);
  };

  const handleEdit = (agent: AgentListItem) => {
    setEditingAgentId(agent.id);
    setIsEditFormOpen(true);
  };

  const handleDeleteConfirm = useCallback(async () => {
    if (!deletingAgentId) return;
    try {
      await deleteAgent(deletingAgentId);
      mutate();
    } catch (err) {
      console.error('Failed to delete agent:', err);
      toast.error(t('delete.error', { fallback: 'Failed to delete agent.' }));
      throw err;
    }
  }, [deletingAgentId, mutate, t]);

  const handleSaveSuccess = () => {
    mutate();
    setIsEditFormOpen(false);
  };

  return (
    <div className="container mx-auto py-8 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('list.title', { fallback: 'My Agents' })}</h1>
          <p className="text-muted-foreground mt-2">
            {t('list.description', {
              fallback: 'Manage your AI assistants and their configurations.',
            })}
          </p>
        </div>
        <Button onClick={handleCreate}>
          <Plus className="mr-2 h-4 w-4" />
          {t('create.button', { fallback: 'Create Agent' })}
        </Button>
      </div>

      {kpi && <FleetKPIBar kpi={kpi} />}

      {error ? (
        <div className="p-4 rounded-xl border bg-destructive/10 text-destructive">
          {t('list.error', { fallback: 'Failed to load agents.' })}
        </div>
      ) : isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-56 rounded-xl border bg-card text-card-foreground shadow animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {sortedAgents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              stats={agentStatsMap[agent.id]}
              locale={locale}
              t={t}
              onEdit={handleEdit}
              onDelete={setDeletingAgentId}
            />
          ))}
          {agents.length === 0 && (
            <div className="col-span-full p-8 text-center border rounded-xl bg-muted/20 text-muted-foreground">
              {t('list.empty', { fallback: 'No agents found. Create one to get started.' })}
            </div>
          )}
        </div>
      )}

      <AgentEditForm
        open={isEditFormOpen}
        onOpenChange={setIsEditFormOpen}
        agentId={editingAgentId}
        onSaveSuccess={handleSaveSuccess}
      />

      <ConfirmDialog
        open={!!deletingAgentId}
        onOpenChange={(open) => {
          if (!open) setDeletingAgentId(null);
        }}
        title={t('delete.title', { fallback: 'Delete Agent' })}
        description={t('delete.confirm', {
          fallback: 'Are you sure you want to delete this agent? This action cannot be undone.',
        })}
        confirmText={t('delete.button', { fallback: 'Delete' })}
        cancelText={t('delete.cancel', { fallback: 'Cancel' })}
        variant="destructive"
        onConfirm={handleDeleteConfirm}
      />
    </div>
  );
}

function FleetKPIBar({ kpi }: { kpi: { onlineAgents: number; monthTokens: number; monthCost: number; pendingApprovals: number } }) {
  const t = useTranslations('Agent.fleet');

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <KPICard
        icon={<Activity className="h-4 w-4 text-green-500" />}
        label={t('kpi.online', { fallback: 'Online' })}
        value={String(kpi.onlineAgents)}
      />
      <KPICard
        icon={<Zap className="h-4 w-4 text-blue-500" />}
        label={t('kpi.monthTokens', { fallback: 'Month Tokens' })}
        value={formatTokens(kpi.monthTokens)}
      />
      <KPICard
        icon={<Coins className="h-4 w-4 text-amber-500" />}
        label={t('kpi.monthCost', { fallback: 'Month Cost' })}
        value={formatCost(kpi.monthCost)}
      />
      <KPICard
        icon={<ShieldAlert className="h-4 w-4 text-orange-500" />}
        label={t('kpi.pending', { fallback: 'Pending' })}
        value={String(kpi.pendingApprovals)}
        highlight={kpi.pendingApprovals > 0}
      />
    </div>
  );
}

function KPICard({ icon, label, value, highlight }: { icon: React.ReactNode; label: string; value: string; highlight?: boolean }) {
  return (
    <div className={`rounded-lg border p-3 flex items-center gap-3 bg-card ${highlight ? 'border-orange-500/50' : ''}`}>
      <div className="shrink-0">{icon}</div>
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground truncate">{label}</p>
        <p className={`text-lg font-semibold tabular-nums ${highlight ? 'text-orange-500' : ''}`}>{value}</p>
      </div>
    </div>
  );
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

function AgentCard({
  agent,
  stats,
  locale,
  t,
  onEdit,
  onDelete,
}: {
  agent: AgentListItem;
  stats: AgentFleetStats | undefined;
  locale: string;
  t: ReturnType<typeof useTranslations>;
  onEdit: (agent: AgentListItem) => void;
  onDelete: (id: string) => void;
}) {
  const status = stats?.status ?? 'idle';

  return (
    <div className="rounded-xl border bg-card text-card-foreground shadow transition-all hover:shadow-md overflow-hidden flex flex-col">
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
