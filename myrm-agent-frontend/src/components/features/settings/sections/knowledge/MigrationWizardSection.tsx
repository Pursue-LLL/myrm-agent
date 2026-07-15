'use client';

/**
 * [INPUT]
 * @/services/migrationDiscovery (POS: external assistant auto-discovery client)
 * @/services/memoryArchive (POS: memory import dry-run / confirm / rollback client)
 *
 * [OUTPUT]
 * MigrationWizardSection: discover → preview → import; honors ?source= deep link auto-preview.
 *
 * [POS]
 * Settings sub-tab under Memory Center. Three-deployment parity.
 * Implements a 3-step wizard: scan/upload → dry-run preview → confirm import.
 * Local/Tauri uses filesystem scan; Cloud shows ZIP upload UI.
 * When URL contains ?source=<id>, auto-starts preview after scan for that source.
 */

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import { toast } from 'sonner';

import {
  discoverMigrationSources,
  importMigrationSecrets,
  invalidateDiscoveryCache,
  uploadMigrationZip,
  type ExternalSource,
  type DiscoveryResponse,
} from '@/services/migrationDiscovery';
import {
  confirmImportMemories,
  dryRunImportMemories,
  rollbackMemoryImport,
  type MemoryImportConfirmResponse,
  type MemoryImportDryRunResponse,
  type MemoryImportPendingSkill,
  type MemoryImportSource,
} from '@/services/memoryArchive';
import { submitSkillMigration, type SkillMigrationSubmitResponse } from '@/services/skillMigration';

import useAgentStore from '@/store/useAgentStore';

import { ScanStep, PreviewStep, ResultStep } from './MigrationWizardSteps';

type WizardStep = 'scan' | 'preview' | 'result';

const MIGRATION_SOURCE_IMPORT_BY_ID: Record<string, MemoryImportSource> = {
  hermes: 'hermes',
  openclaw: 'openclaw',
  codex: 'codex',
  claude: 'claude',
  chatgpt: 'chatgpt',
};

function resolveMigrationImportSource(competitor: string): MemoryImportSource {
  return MIGRATION_SOURCE_IMPORT_BY_ID[competitor.trim().toLowerCase()] ?? 'auto';
}

interface MigrationWizardSectionProps {
  onMigrationComplete?: () => void;
}

const MigrationWizardSection = memo(({ onMigrationComplete }: MigrationWizardSectionProps) => {
  const t = useTranslations('memory.migrationWizard');
  const searchParams = useSearchParams();
  const deepLinkSourceId = searchParams.get('source')?.trim().toLowerCase() ?? '';
  const deepLinkPreviewAttemptedRef = useRef(false);

  const [step, setStep] = useState<WizardStep>('scan');
  const [scanning, setScanning] = useState(false);
  const [discovery, setDiscovery] = useState<DiscoveryResponse | null>(null);

  const [selectedSource, setSelectedSource] = useState<ExternalSource | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [dryRunResult, setDryRunResult] = useState<MemoryImportDryRunResponse | null>(null);
  const [importSecrets, setImportSecrets] = useState(false);
  const [includeEpisodic, setIncludeEpisodic] = useState(false);
  const [targetAgentId, setTargetAgentId] = useState<string | null>(null);

  const agents = useAgentStore((state) => state.agents);
  const fetchAgents = useAgentStore((state) => state.fetchAgents);

  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<MemoryImportConfirmResponse | null>(null);
  const [skillSubmitResult, setSkillSubmitResult] = useState<SkillMigrationSubmitResponse | null>(null);
  const [skillSubmitFailed, setSkillSubmitFailed] = useState(false);
  const [secretsImportMessage, setSecretsImportMessage] = useState<string | null>(null);
  const [rollingBack, setRollingBack] = useState(false);
  const [retryingSkills, setRetryingSkills] = useState(false);

  const handleScan = useCallback(
    async (force = false) => {
      setScanning(true);
      try {
        if (force) invalidateDiscoveryCache();
        const result = await discoverMigrationSources(force);
        setDiscovery(result);
      } catch {
        toast.error(t('scanFailed'));
      } finally {
        setScanning(false);
      }
    },
    [t],
  );

  const [uploading, setUploading] = useState(false);

  const handleUpload = useCallback(
    async (file: File) => {
      setUploading(true);
      try {
        const result = await uploadMigrationZip(file);
        setDiscovery(result);
        if (result.sources.length === 0) {
          toast.info(t('cloudUploadEmpty'));
        }
      } catch {
        toast.error(t('cloudUploadFailed'));
      } finally {
        setUploading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    void handleScan();
    void fetchAgents(1, 50, true);
  }, [handleScan, fetchAgents]);

  const handlePreview = useCallback(
    async (source: ExternalSource): Promise<boolean> => {
      setSelectedSource(source);
      setPreviewing(true);
      setImportSecrets(false);
      try {
        const payload = {
          competitor: source.competitor,
          root: source.root,
          files: source.files.map((f) => f.path),
        };
        const result = await dryRunImportMemories(
          payload,
          resolveMigrationImportSource(source.competitor),
          {
          target_agent_id: targetAgentId,
          clone_from_agent_id: 'builtin-general',
          include_episodic: source.competitor === 'chatgpt' || (source.competitor === 'openclaw' && includeEpisodic),
          apply_global_instructions: true,
          },
        );
        setDryRunResult(result);
        setStep('preview');
        return true;
      } catch {
        toast.error(t('previewFailed'));
        return false;
      } finally {
        setPreviewing(false);
      }
    },
    [includeEpisodic, targetAgentId, t],
  );

  useEffect(() => {
    if (
      !deepLinkSourceId ||
      !discovery ||
      scanning ||
      previewing ||
      step !== 'scan' ||
      deepLinkPreviewAttemptedRef.current
    ) {
      return;
    }

    if (!(deepLinkSourceId in MIGRATION_SOURCE_IMPORT_BY_ID)) {
      deepLinkPreviewAttemptedRef.current = true;
      toast.error(t('deepLinkSourceInvalid'));
      return;
    }

    const matched = discovery.sources.find((source) => source.competitor.toLowerCase() === deepLinkSourceId);
    if (!matched) {
      deepLinkPreviewAttemptedRef.current = true;
      toast.error(t('deepLinkSourceNotFound'));
      return;
    }

    deepLinkPreviewAttemptedRef.current = true;
    void handlePreview(matched).then((ok) => {
      if (!ok) {
        deepLinkPreviewAttemptedRef.current = false;
      }
    });
  }, [deepLinkSourceId, discovery, scanning, previewing, step, handlePreview, t]);

  const submitPendingSkills = useCallback(
    async (pendingSkills: MemoryImportPendingSkill[], bindAgentId: string | null | undefined) => {
      if (!selectedSource || pendingSkills.length === 0) {
        return;
      }
      const skillResult = await submitSkillMigration({
        source: selectedSource.competitor,
        skills: pendingSkills.map((skill) => ({ ...skill })),
        description: `Assistant import from ${selectedSource.competitor}`,
        target_agent_id: bindAgentId ?? null,
      });
      setSkillSubmitResult(skillResult);
      setSkillSubmitFailed(false);
    },
    [selectedSource],
  );

  const handleConfirmImport = useCallback(async () => {
    if (!dryRunResult || !selectedSource) return;
    setImporting(true);
    setSkillSubmitFailed(false);
    setSecretsImportMessage(null);
    try {
      const result = await confirmImportMemories(dryRunResult.dry_run_id);
      setImportResult(result);

      const pendingSkills: MemoryImportPendingSkill[] = dryRunResult.pending_skills ?? [];
      if (pendingSkills.length > 0) {
        try {
          await submitPendingSkills(pendingSkills, result.target_agent_id ?? targetAgentId);
        } catch {
          setSkillSubmitFailed(true);
          setSkillSubmitResult(null);
          toast.warning(t('skillsSubmitFailed'));
        }
      } else {
        setSkillSubmitResult(null);
      }

      if (importSecrets && selectedSource.has_api_keys) {
        try {
          const secretsResult = await importMigrationSecrets(selectedSource.competitor, selectedSource.root);
          setSecretsImportMessage(secretsResult.message);
          if (secretsResult.imported_keys.length > 0) {
            toast.success(t('secretsImportSuccess', { count: secretsResult.imported_keys.length }));
          } else if ((secretsResult.skipped_keys?.length ?? 0) > 0) {
            toast.warning(t('secretsImportPartialSkip'));
          }
        } catch {
          toast.warning(t('secretsImportFailed'));
        }
      }

      setStep('result');
      invalidateDiscoveryCache();
      onMigrationComplete?.();
    } catch {
      toast.error(t('importFailed'));
    } finally {
      setImporting(false);
    }
  }, [dryRunResult, selectedSource, importSecrets, targetAgentId, onMigrationComplete, submitPendingSkills, t]);

  const handleRetrySkillSubmit = useCallback(async () => {
    if (!dryRunResult || !importResult) return;
    const pendingSkills = dryRunResult.pending_skills ?? [];
    if (pendingSkills.length === 0) return;
    setRetryingSkills(true);
    try {
      await submitPendingSkills(pendingSkills, importResult.target_agent_id ?? targetAgentId);
      toast.success(t('result.skillsRetrySuccess'));
    } catch {
      setSkillSubmitFailed(true);
      toast.warning(t('skillsSubmitFailed'));
    } finally {
      setRetryingSkills(false);
    }
  }, [dryRunResult, importResult, submitPendingSkills, targetAgentId, t]);

  const handleRollback = useCallback(async () => {
    if (!importResult) return;
    const deleteImportedAgent = importResult.agent_created && window.confirm(t('result.rollbackDeleteAgentConfirm'));
    setRollingBack(true);
    try {
      const rollbackResult = await rollbackMemoryImport(importResult.import_batch_id, {
        deleteImportedAgent,
      });
      if (rollbackResult.imported_agent_deleted) {
        toast.success(t('result.rollbackAgentDeleted'));
      } else if (rollbackResult.instructions_rolled_back) {
        toast.success(t('result.rollbackIncludesInstructions'));
      } else {
        toast.success(t('rollbackSuccess'));
      }
      setStep('scan');
      setDryRunResult(null);
      setImportResult(null);
      setSkillSubmitResult(null);
      setSkillSubmitFailed(false);
      setSecretsImportMessage(null);
      void handleScan(true);
    } catch {
      toast.error(t('rollbackFailed'));
    } finally {
      setRollingBack(false);
    }
  }, [importResult, handleScan, t]);

  const handleBackToScan = useCallback(() => {
    setStep('scan');
    setDryRunResult(null);
    setSelectedSource(null);
    setSkillSubmitResult(null);
    setSkillSubmitFailed(false);
    setSecretsImportMessage(null);
    setImportSecrets(false);
  }, []);

  return (
    <div className="space-y-6 max-w-4xl">
      {step === 'scan' && (
        <ScanStep
          discovery={discovery}
          scanning={scanning}
          uploading={uploading}
          previewing={previewing}
          previewingSource={selectedSource}
          includeEpisodic={includeEpisodic}
          onIncludeEpisodicChange={setIncludeEpisodic}
          agents={agents}
          targetAgentId={targetAgentId}
          onTargetAgentIdChange={setTargetAgentId}
          onScan={() => handleScan(true)}
          onUpload={handleUpload}
          onPreview={handlePreview}
          t={t}
        />
      )}
      {step === 'preview' && dryRunResult && selectedSource && (
        <PreviewStep
          source={selectedSource}
          dryRun={dryRunResult}
          importing={importing}
          importSecrets={importSecrets}
          onImportSecretsChange={setImportSecrets}
          onConfirm={handleConfirmImport}
          onBack={handleBackToScan}
          t={t}
        />
      )}
      {step === 'result' && importResult && (
        <ResultStep
          result={importResult}
          skillSubmitResult={skillSubmitResult}
          skillSubmitFailed={skillSubmitFailed}
          secretsImportMessage={secretsImportMessage}
          rollingBack={rollingBack}
          onRollback={handleRollback}
          onRetrySkillSubmit={handleRetrySkillSubmit}
          retryingSkills={retryingSkills}
          onDone={handleBackToScan}
          t={t}
        />
      )}
    </div>
  );
});

MigrationWizardSection.displayName = 'MigrationWizardSection';
export default MigrationWizardSection;
