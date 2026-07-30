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
  getSecondBrainPresetStatus,
  type SecondBrainChecklistItem,
  type SecondBrainPresetStatus,
} from '@/services/onboarding';

interface SecondBrainSetupCardProps {
  onApplied?: (agentId: string) => void;
  onGoToImport?: () => void;
  onGoToProviders?: () => void;
}

function ChecklistRow({ item, label }: { item: SecondBrainChecklistItem; label: string }) {
  return (
    <li className="flex items-start gap-2 text-sm">
      <span
        className={cn(
          'mt-1.5 inline-flex h-2 w-2 shrink-0 rounded-full',
          item.ready ? 'bg-emerald-500' : 'bg-muted-foreground/40',
        )}
        aria-hidden
      />
      <span className={cn(item.ready ? 'text-foreground' : 'text-muted-foreground')}>{label}</span>
    </li>
  );
}

export default function SecondBrainSetupCard({
  onApplied,
  onGoToImport,
  onGoToProviders,
}: SecondBrainSetupCardProps) {
  const t = useTranslations('settings.wiki.secondBrain');
  const [status, setStatus] = useState<SecondBrainPresetStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);

  const refreshStatus = useCallback(async () => {
    setLoading(true);
    try {
      const next = await getSecondBrainPresetStatus();
      setStatus(next);
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
    provider_ready: t('checklist.providerReady'),
  };

  const vaultReady = status?.checklist.find((item) => item.id === 'vault_content')?.ready ?? false;
  const providerReady = status?.checklist.find((item) => item.id === 'provider_ready')?.ready ?? false;

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
              <p className="text-sm text-muted-foreground">
                {t('appliedAs', { name: status.agent_name })}
              </p>
            ) : null}
            <ul className="space-y-2">
              {(status?.checklist ?? []).map((item) => (
                <ChecklistRow key={item.id} item={item} label={checklistLabels[item.id]} />
              ))}
            </ul>
            <div className="flex flex-wrap gap-2">
              <Button onClick={handleApply} disabled={applying}>
                {applying ? t('applying') : status?.applied ? t('reapply') : t('apply')}
              </Button>
              {status?.applied && status.agent_id ? (
                <Button
                  variant="outline"
                  onClick={() => void selectSecondBrainAgent(status.agent_id!)}
                >
                  {t('useAgent')}
                </Button>
              ) : null}
              {!vaultReady && onGoToImport ? (
                <Button variant="outline" onClick={onGoToImport}>
                  {t('goImport')}
                </Button>
              ) : null}
              {!providerReady && onGoToProviders ? (
                <Button variant="outline" onClick={onGoToProviders}>
                  {t('goProviders')}
                </Button>
              ) : null}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
