'use client';

import React, { useState, useCallback, useMemo } from 'react';
import useSWR from 'swr';
import { AgentEditForm } from '@/components/agent/AgentEditForm';
import { AgentSetupWizard } from '@/components/agent/AgentSetupWizard';
import { GovernancePanel } from '@/components/agent/GovernancePanel';
import { Button } from '@/components/primitives/button';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import {
  Plus,
  Sparkles,
  Bot,
  Store,
} from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { listAgents, deleteAgent, getFleetOverview, AgentListItem, AgentFleetStats } from '@/services/agent';
import { toast } from '@/hooks/shared/useToast';
import { AgentCard } from './AgentCard';
import { FleetKPIBar } from './FleetKPIBar';
import { AgentTemplateMarketplace } from '@/components/features/templates';

const EMPTY_AGENTS: AgentListItem[] = [];
const EMPTY_AGENT_STATS: Record<string, AgentFleetStats> = {};

export default function AgentsPage() {
  const t = useTranslations('Agent');
  const locale = useLocale();

  const [activeTab, setActiveTab] = useState<'my-agents' | 'marketplace'>('my-agents');
  const [isEditFormOpen, setIsEditFormOpen] = useState(false);
  const [isSetupWizardOpen, setIsSetupWizardOpen] = useState(false);
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null);
  const [deletingAgentId, setDeletingAgentId] = useState<string | null>(null);

  const { data: response, error, isLoading, mutate } = useSWR('listAgents', () => listAgents(1, 100));
  const { data: fleetData } = useSWR('fleetOverview', getFleetOverview, {
    refreshInterval: 5_000,
    revalidateOnFocus: true,
  });

  const agents = response?.items || EMPTY_AGENTS;
  const kpi = fleetData?.kpi;
  const agentStatsMap = fleetData?.agents || EMPTY_AGENT_STATS;

  const agentNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const a of agents) {
      map[a.id] = a.name;
    }
    return map;
  }, [agents]);

  const handleReview = (agentId: string) => {
    setEditingAgentId(agentId);
    setIsEditFormOpen(true);
  };

  const sortedAgents = useMemo(() => {
    if (!agents.length) {
      return agents;
    }
    return [...agents].sort((a, b) => {
      const sa = agentStatsMap[a.id];
      const sb = agentStatsMap[b.id];
      const statusA = sa?.status === 'busy' ? 0 : 1;
      const statusB = sb?.status === 'busy' ? 0 : 1;
      if (statusA !== statusB) {
        return statusA - statusB;
      }
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
    if (!deletingAgentId) {
      return;
    }
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

  const handleTemplateAgentCreated = (_createdAgent: { id: string; name: string }) => {
    mutate();
    setActiveTab('my-agents');
    toast.success(t('create.success', { fallback: 'Agent created successfully from template!' }));
  };

  return (
    <div className="container mx-auto py-8 max-w-5xl">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('list.title', { fallback: 'My Agents' })}</h1>
          <p className="text-muted-foreground mt-2">
            {t('list.description', {
              fallback: 'Manage your AI assistants and their configurations.',
            })}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setIsSetupWizardOpen(true)}>
            <Sparkles className="mr-2 h-4 w-4" />
            {t('setupWizard.open', { fallback: 'Guided setup' })}
          </Button>
          <Button onClick={handleCreate}>
            <Plus className="mr-2 h-4 w-4" />
            {t('create.button', { fallback: 'Create Agent' })}
          </Button>
        </div>
      </div>

      {/* Tabs navigation: My Agents vs App Marketplace */}
      <div className="flex items-center gap-2 border-b border-border mb-6">
        <button
          type="button"
          onClick={() => setActiveTab('my-agents')}
          data-testid="tab-my-agents"
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'my-agents'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Bot className="h-4 w-4" />
          <span>{t('list.title', { fallback: 'My Agents' })} ({agents.length})</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('marketplace')}
          data-testid="tab-template-marketplace"
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'marketplace'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Store className="h-4 w-4 text-amber-500" />
          <span>Marketplace</span>
          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-600 dark:text-amber-400">
            20+ Prebuilt
          </span>
        </button>
      </div>

      {activeTab === 'marketplace' ? (
        <AgentTemplateMarketplace onAgentCreated={handleTemplateAgentCreated} />
      ) : (
        <>
          {kpi && <FleetKPIBar kpi={kpi} />}

          <GovernancePanel agentNames={agentNames} onReview={handleReview} onChanged={mutate} />

          {error ? (
            <div className="p-4 rounded-xl border bg-destructive/10 text-destructive">
              {t('list.error', { fallback: 'Failed to load agents.' })}
            </div>
          ) : isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-56 rounded-xl border bg-card text-card-foreground shadow-xs animate-pulse" />
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
        </>
      )}

      <AgentEditForm
        open={isEditFormOpen}
        onOpenChange={setIsEditFormOpen}
        agentId={editingAgentId}
        onSaveSuccess={handleSaveSuccess}
      />

      <AgentSetupWizard open={isSetupWizardOpen} onOpenChange={setIsSetupWizardOpen} onDone={mutate} />

      <ConfirmDialog
        open={!!deletingAgentId}
        onOpenChange={(open) => {
          if (!open) {
            setDeletingAgentId(null);
          }
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
