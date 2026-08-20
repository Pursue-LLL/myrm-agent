'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { cn } from '@/lib/utils/classnameUtils';
import { buildAgentConfig } from '@/lib/utils/agentConfigMapper';
import useChatStore from '@/store/useChatStore';
import useAgentStore from '@/store/useAgentStore';
import {
  applySecondBrainPreset,
  getReadinessStatus,
  getSecondBrainPresetStatus,
  type SecondBrainChecklistItem,
  type SecondBrainPresetStatus,
} from '@/services/onboarding';
import SecondBrainPitfallGuardrails from './SecondBrainPitfallGuardrails';

interface SecondBrainSetupCardProps {
  onApplied?: (agentId: string) => void;
  onGoToImport?: () => void;
  onGoToProviders?: () => void;
  onGoToDuplicateReview?: () => void;
  onGoToGraph?: () => void;
}

function ChecklistRow({
  item,
  label,
  hint,
  providerMissing,
}: {
  item: SecondBrainChecklistItem;
  label: string;
  hint: string;
  providerMissing?: string[];
}) {
  return (
    <li className="space-y-1" data-testid={`second-brain-checklist-${item.id}`}>
      <div className="flex items-start gap-2 text-sm">
        <span
          className={cn(
            'mt-1.5 inline-flex h-2 w-2 shrink-0 rounded-full',
            item.ready ? 'bg-emerald-500' : 'bg-muted-foreground/40',
          )}
          aria-hidden
        />
        <span className={cn(item.ready ? 'text-foreground' : 'text-muted-foreground')}>{label}</span>
      </div>
      {!item.ready ? (
        <div className="ml-4 space-y-1">
          <p
            className="text-xs leading-relaxed text-muted-foreground"
            data-testid={`second-brain-pitfall-hint-${item.id}`}
          >
            {hint}
          </p>
          {item.id === 'provider_ready' && providerMissing && providerMissing.length > 0 ? (
            <ul className="list-disc pl-4 text-xs text-muted-foreground">
              {providerMissing.map((entry) => (
                <li key={entry}>{entry}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

export default function SecondBrainSetupCard({
  onApplied,
  onGoToImport,
  onGoToProviders,
  onGoToDuplicateReview,
  onGoToGraph,
}: SecondBrainSetupCardProps) {
  const t = useTranslations('settings.wiki.secondBrain');
  const [status, setStatus] = useState<SecondBrainPresetStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [providerMissing, setProviderMissing] = useState<string[]>([]);

  const refreshStatus = useCallback(async () => {
    setLoading(true);
    try {
      const next = await getSecondBrainPresetStatus();
      setStatus(next);
      const providerItem = next.checklist.find((item) => item.id === 'provider_ready');
      if (providerItem && !providerItem.ready) {
        try {
          const readiness = await getReadinessStatus();
          setProviderMissing(readiness.provider.missing_items ?? []);
        } catch {
          setProviderMissing([]);
        }
      } else {
        setProviderMissing([]);
      }
    } catch {
      toast.error(t('loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  const selectSecondBrainAgent = useCallback(async (agentId: string) => {
    try {
      const fullAgent = await useAgentStore.getState().fetchAgent(agentId);
      if (!fullAgent) {
        return;
      }
      useChatStore.getState().setActionMode('agent');
      useChatStore.getState().setAgentConfig(buildAgentConfig(fullAgent));
    } catch (error) {
      console.warn('Failed to select Second Brain agent:', error);
    }
  }, []);

  const handleApply = async () => {
    setApplying(true);
    try {
      const result = await applySecondBrainPreset();
      setStatus({
        applied: true,
        agent_id: result.agent_id,
        agent_name: result.agent_name,
        cron_job_id: result.cron_job_id,
        delta_cron_job_id: result.delta_cron_job_id,
        applied_at: result.applied_at,
        checklist: result.checklist,
      });
      await selectSecondBrainAgent(result.agent_id);
      toast.success(result.message);
      onApplied?.(result.agent_id);
      void refreshStatus();
    } catch {
      toast.error(t('applyFailed'));
    } finally {
      setApplying(false);
    }
  };

  const checklistLabels: Record<SecondBrainChecklistItem['id'], string> = {
    agent_tools: t('checklist.agentTools'),
    cron_job: t('checklist.cronJob'),
    vault_content: t('checklist.vaultContent'),
    corpus_dedup: t('checklist.corpusDedup'),
    provider_ready: t('checklist.providerReady'),
  };

  const pitfallHints: Record<SecondBrainChecklistItem['id'], string> = {
    agent_tools: t('pitfalls.checklist.agentTools'),
    cron_job: t('pitfalls.checklist.cronJob'),
    vault_content: t('pitfalls.checklist.vaultContent'),
    corpus_dedup: t('pitfalls.checklist.corpusDedup'),
    provider_ready: t('pitfalls.checklist.providerReady'),
  };

  const vaultReady = status?.checklist.find((item) => item.id === 'vault_content')?.ready ?? false;
  const corpusDedupReady = status?.checklist.find((item) => item.id === 'corpus_dedup')?.ready ?? false;
  const providerReady = status?.checklist.find((item) => item.id === 'provider_ready')?.ready ?? false;
  const agentToolsReady = status?.checklist.find((item) => item.id === 'agent_tools')?.ready ?? false;
  const cronReady = status?.checklist.find((item) => item.id === 'cron_job')?.ready ?? false;

  const handleUseAgent = () => {
    if (status?.agent_id) {
      void selectSecondBrainAgent(status.agent_id);
    }
  };

  return (
    <Card className="border-primary/20 bg-gradient-to-br from-primary/5 via-background to-accent-warm/5">
      <CardHeader>
        <CardTitle>{t('title')}</CardTitle>
        <CardDescription>{t('description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <p className="text-sm text-muted-foreground">{t('loading')}</p>
        ) : (
          <>
            {status?.applied && status.agent_name ? (
              <p className="text-sm text-muted-foreground">{t('appliedAs', { name: status.agent_name })}</p>
            ) : null}
            <ul className="space-y-3">
              {(status?.checklist ?? []).map((item) => (
                <ChecklistRow
                  key={item.id}
                  item={item}
                  label={checklistLabels[item.id]}
                  hint={pitfallHints[item.id]}
                  providerMissing={item.id === 'provider_ready' ? providerMissing : undefined}
                />
              ))}
            </ul>
            <div className="flex flex-wrap gap-2">
              <Button onClick={handleApply} disabled={applying}>
                {applying ? t('applying') : status?.applied ? t('reapply') : t('apply')}
              </Button>
              {status?.applied && status.agent_id ? (
                <Button variant="outline" onClick={() => void selectSecondBrainAgent(status.agent_id!)}>
                  {t('useAgent')}
                </Button>
              ) : null}
              {(!agentToolsReady || !cronReady) && status?.applied ? (
                <Button variant="outline" onClick={() => void handleApply()} disabled={applying}>
                  {t('pitfalls.actions.repairPreset')}
                </Button>
              ) : null}
              {!vaultReady && onGoToImport ? (
                <Button variant="outline" onClick={onGoToImport}>
                  {t('goImport')}
                </Button>
              ) : null}
              {!corpusDedupReady && onGoToDuplicateReview ? (
                <Button variant="outline" onClick={onGoToDuplicateReview}>
                  {t('goDuplicateReview')}
                </Button>
              ) : null}
              {!providerReady && onGoToProviders ? (
                <Button variant="outline" onClick={onGoToProviders} data-testid="second-brain-go-providers">
                  {t('goProviders')}
                </Button>
              ) : null}
              {vaultReady && onGoToGraph ? (
                <Button variant="outline" onClick={onGoToGraph} data-testid="wiki-go-graph-btn">
                  {t('goGraph')}
                </Button>
              ) : null}
            </div>
          </>
        )}
        <SecondBrainPitfallGuardrails
          agentId={status?.agent_id}
          onUseAgent={handleUseAgent}
          onGoToImport={onGoToImport}
        />
      </CardContent>
    </Card>
  );
}
