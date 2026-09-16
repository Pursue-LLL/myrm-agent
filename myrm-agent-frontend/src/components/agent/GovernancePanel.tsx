'use client';

import React, { useState } from 'react';
import useSWR from 'swr';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Archive, GitMerge, ShieldCheck, Trash2 } from 'lucide-react';
import {
  deleteAgent,
  getGovernanceOverview,
  type GovernanceOverview,
} from '@/services/agent';
import { toast } from '@/hooks/shared/useToast';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { MergeWizard } from '@/components/agent/GovernanceMergeWizard';

interface GovernancePanelProps {
  agentNames: Record<string, string>;
  onReview: (agentId: string) => void;
  onChanged: () => void;
}

export function GovernancePanel({ agentNames, onReview, onChanged }: GovernancePanelProps) {
  const t = useTranslations('Agent.governance');
  const tAgent = useTranslations('Agent');
  const { data, isLoading, mutate } = useSWR('governanceOverview', getGovernanceOverview, {
    revalidateOnFocus: false,
  });
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const refresh = () => {
    mutate();
    onChanged();
  };

  const handleDeleteConfirm = async () => {
    if (!deletingId) {
      return;
    }
    try {
      await deleteAgent(deletingId);
      setDeletingId(null);
      refresh();
    } catch {
      toast.error(tAgent('delete.error', { fallback: 'Failed to delete agent.' }));
      throw new Error('delete-failed');
    }
  };

  if (isLoading || !data || !data.needs_attention) {
    return null;
  }

  return (
    <section className="rounded-xl border bg-card p-5 mb-6" aria-label="Agent governance">
      <div className="flex items-center gap-2 mb-1">
        <ShieldCheck className="h-4 w-4 text-primary" />
        <h2 className="text-base font-semibold">
          {t('title', { fallback: 'Agent Health Check' })}
        </h2>
      </div>
      <p className="text-sm text-muted-foreground mb-4">
        {t('subtitle', {
          fallback: 'Unused assistants and overlapping responsibilities, with safe one-click cleanup.',
        })}
      </p>

      {data.orphans.length > 0 && (
        <div className="mb-4">
          <p className="text-sm font-medium mb-2">
            {t('orphans', { fallback: 'Unused assistants' })} ({data.orphans.length})
          </p>
          <ul className="space-y-2">
            {data.orphans.map((orphan) => (
              <li
                key={orphan.id}
                className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-lg border border-border/60 p-3"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{orphan.name}</p>
                  <p className="text-xs text-muted-foreground">{orphan.reason}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" className="h-8" onClick={() => onReview(orphan.id)}>
                    <Archive className="mr-2 h-4 w-4" />
                    {t('review', { fallback: 'Review' })}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 text-destructive hover:text-destructive"
                    onClick={() => setDeletingId(orphan.id)}
                    aria-label={tAgent('delete.button', { fallback: 'Delete' })}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <ConfirmDialog
        open={!!deletingId}
        onOpenChange={(open) => {
          if (!open) {
            setDeletingId(null);
          }
        }}
        title={tAgent('delete.title', { fallback: 'Delete Agent' })}
        description={tAgent('delete.confirm', {
          fallback: 'Are you sure you want to delete this agent? This action cannot be undone.',
        })}
        confirmText={tAgent('delete.button', { fallback: 'Delete' })}
        cancelText={tAgent('delete.cancel', { fallback: 'Cancel' })}
        variant="destructive"
        onConfirm={handleDeleteConfirm}
      />

      {data.overlaps.length > 0 && (
        <div>
          <p className="text-sm font-medium mb-2">
            {t('overlaps', { fallback: 'Overlapping responsibilities' })} ({data.overlaps.length})
          </p>
          <ul className="space-y-2">
            {data.overlaps.map((pair) => (
              <OverlapRow
                key={`${pair.agent_a.id}-${pair.agent_b.id}`}
                pair={pair}
                agentNames={agentNames}
                onDone={() => {
                  mutate();
                  onChanged();
                }}
              />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function OverlapRow({
  pair,
  agentNames,
  onDone,
}: {
  pair: GovernanceOverview['overlaps'][number];
  agentNames: Record<string, string>;
  onDone: () => void;
}) {
  const t = useTranslations('Agent.governance');
  const [wizardOpen, setWizardOpen] = useState(false);
  return (
    <li className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-lg border border-border/60 p-3">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">
          {agentNames[pair.agent_a.id] || pair.agent_a.name}
          <span className="text-muted-foreground font-normal"> + </span>
          {agentNames[pair.agent_b.id] || pair.agent_b.name}
        </p>
        <p className="text-xs text-muted-foreground truncate">
          {t('sharedSkills', { fallback: 'Shared skills' })}: {pair.shared_skills.join(', ') || '—'}
        </p>
      </div>
      <Button variant="outline" size="sm" className="h-8" onClick={() => setWizardOpen(true)}>
        <GitMerge className="mr-2 h-4 w-4" />
        {t('merge', { fallback: 'Merge' })}
      </Button>
      {wizardOpen && <MergeWizard pair={pair} agentNames={agentNames} onClose={() => setWizardOpen(false)} onDone={onDone} />}
    </li>
  );
}
