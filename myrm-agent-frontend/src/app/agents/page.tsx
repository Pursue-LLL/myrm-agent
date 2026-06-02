'use client';

import React, { useState, useCallback } from 'react';
import useSWR from 'swr';
import { AgentAvatar } from '@/components/agent/AgentAvatar';
import { AgentEditForm } from '@/components/agent/AgentEditForm';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Plus, Settings, Trash2 } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import { listAgents, deleteAgent, AgentListItem } from '@/services/agent';
import { getBuiltinAgentName, getBuiltinAgentDescription } from '@/components/agent/builtin-agent-i18n';
import { toast } from '@/hooks/useToast';

export default function AgentsPage() {
  const t = useTranslations('Agent');
  const locale = useLocale();

  const [isEditFormOpen, setIsEditFormOpen] = useState(false);
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null);
  const [deletingAgentId, setDeletingAgentId] = useState<string | null>(null);

  const { data: response, error, isLoading, mutate } = useSWR('listAgents', () => listAgents(1, 100));

  const agents = response?.items || [];

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
    // Revalidate SWR cache after create/update
    mutate();
    setIsEditFormOpen(false);
  };

  return (
    <div className="container mx-auto py-8 max-w-5xl">
      <div className="flex items-center justify-between mb-8">
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

      {error ? (
        <div className="p-4 rounded-xl border bg-destructive/10 text-destructive">
          {t('list.error', { fallback: 'Failed to load agents.' })}
        </div>
      ) : isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-48 rounded-xl border bg-card text-card-foreground shadow animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {agents.map((agent) => (
            <div
              key={agent.id}
              className="rounded-xl border bg-card text-card-foreground shadow transition-all hover:shadow-md overflow-hidden flex flex-col"
            >
              <div className="p-6 flex-1">
                <div className="flex items-start justify-between">
                  <AgentAvatar url={agent.avatar_url} name={agent.name} agentId={agent.id} size="lg" />
                  {agent.is_built_in && (
                    <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 border-transparent bg-secondary text-secondary-foreground">
                      {t('builtin', { fallback: 'Built-in' })}
                    </span>
                  )}
                </div>
                <h3 className="text-lg font-semibold mt-4">{getBuiltinAgentName(agent.id, agent.name, locale)}</h3>
                <p className="text-sm text-muted-foreground mt-2 line-clamp-2">
                  {getBuiltinAgentDescription(agent.id, agent.description || '', locale) ||
                    t('noDescription', { fallback: 'No description provided.' })}
                </p>
              </div>
              <div className="bg-muted/50 p-4 flex items-center justify-end gap-2 border-t">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8"
                  onClick={() => window.open(`/?agent_id=${agent.id}`, '_blank', 'noopener,noreferrer')}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="mr-2 h-4 w-4"
                  >
                    <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z" />
                  </svg>
                  {t('testChat', { fallback: 'Test Chat' })}
                </Button>
                <Button variant="ghost" size="sm" className="h-8" onClick={() => handleEdit(agent)}>
                  <Settings className="mr-2 h-4 w-4" />
                  {t('settings', { fallback: 'Settings' })}
                </Button>
                {!agent.is_built_in && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 text-destructive hover:text-destructive"
                    onClick={() => setDeletingAgentId(agent.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
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
