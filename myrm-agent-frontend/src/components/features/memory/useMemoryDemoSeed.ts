'use client';

import { useCallback, useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/useToast';
import { dryRunImportMemories, confirmImportMemories, rollbackMemoryImport } from '@/services/memoryArchive';
import { getConfigSyncManager } from '@/services/config';

const DEMO_BATCH_ID_KEY = 'myrm_demo_batch_id';

export const useMemoryDemoSeed = ({
  setActionId,
  loadSnapshot,
}: {
  setActionId: (actionId: string | null) => void;
  loadSnapshot: () => Promise<void>;
}) => {
  const t = useTranslations('memory');
  const [isSeeding, setIsSeeding] = useState(false);
  const [isRollingBack, setIsRollingBack] = useState(false);
  const [demoBatchId, setDemoBatchId] = useState<string | null>(null);

  useEffect(() => {
    const storedBatchId = localStorage.getItem(DEMO_BATCH_ID_KEY);
    if (storedBatchId) {
      setDemoBatchId(storedBatchId);
    }
  }, []);

  const seedDemoData = useCallback(async () => {
    setIsSeeding(true);
    setActionId('demo:seed');
    try {
      // 0. Pre-flight Check: Check if Embedding Service is ready
      const configManager = getConfigSyncManager();
      const retrievalConfig = configManager.get('retrieval');
      if (!retrievalConfig?.embeddingApplied) {
        toast({
          title: t('commandCenter.embeddingNotReady', { fallback: 'Embedding Service Not Ready' }),
          description: t('commandCenter.embeddingNotReadyDesc', {
            fallback: 'Please configure an embedding model in Settings > Model Service before using the Demo.',
          }),
          variant: 'destructive',
        });
        return;
      }

      // 1. Fetch the demo JSON
      const response = await fetch('/demo/demo_memory_snapshot.json');
      if (!response.ok) {
        throw new Error('Failed to fetch demo data');
      }
      const demoData = await response.json();

      // 2. Dry run import
      const dryRunResult = await dryRunImportMemories(demoData, 'native_json');

      // 3. Confirm import
      const confirmResult = await confirmImportMemories(dryRunResult.dry_run_id);

      // Store batch ID for rollback
      const batchId = confirmResult.import_batch_id;
      localStorage.setItem(DEMO_BATCH_ID_KEY, batchId);
      setDemoBatchId(batchId);

      toast({
        title: t('commandCenter.demoSeedSuccess', { fallback: 'Demo data seeded successfully!' }),
        description: t('commandCenter.demoSeedSuccessDesc', {
          fallback: 'You can now explore the memory graph and semantic search.',
        }),
      });

      // 4. Refresh command center
      await loadSnapshot();
    } catch (err) {
      toast({
        title: t('commandCenter.actionFailed'),
        description: err instanceof Error ? err.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsSeeding(false);
      setActionId(null);
    }
  }, [loadSnapshot, setActionId, t]);

  const rollbackDemoData = useCallback(async () => {
    if (!demoBatchId) return;

    setIsRollingBack(true);
    setActionId('demo:rollback');
    try {
      await rollbackMemoryImport(demoBatchId);

      localStorage.removeItem(DEMO_BATCH_ID_KEY);
      setDemoBatchId(null);

      toast({
        title: t('commandCenter.demoRollbackSuccess', { fallback: 'Demo data removed successfully!' }),
      });

      await loadSnapshot();
    } catch (err) {
      toast({
        title: t('commandCenter.actionFailed'),
        description: err instanceof Error ? err.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsRollingBack(false);
      setActionId(null);
    }
  }, [demoBatchId, loadSnapshot, setActionId, t]);

  return { seedDemoData, isSeeding, rollbackDemoData, isRollingBack, hasDemoData: !!demoBatchId };
};
