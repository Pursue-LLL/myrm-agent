'use client';

import { memo, useState, useEffect, useCallback, useId } from 'react';
import { useTranslations } from 'next-intl';
import { Play, Loader2, Combine, AlertTriangle, Video } from 'lucide-react';
import { WorkflowRecorderModal } from './WorkflowRecorderModal';
import CuratorNumberField from './CuratorNumberField';
import CuratorDiagnosticsSection from './CuratorDiagnosticsSection';
import CuratorHistorySection from './CuratorHistorySection';
import { Switch } from '@/components/primitives/switch';
import { Label } from '@/components/primitives/label';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { toast } from '@/hooks/shared/useToast';
import {
  getCuratorConfig,
  updateCuratorConfig,
  runCuratorSweep,
  getCuratorHistory,
  getConsolidationPreview,
  executeConsolidation,
  getSkillDiagnostics,
  remediateSkillFinding,
  type CuratorConfigResponse,
  type CuratorHistoryEntry,
  type ConsolidationPreviewResponse,
  type ConsolidationExecuteResponse,
  type SkillDoctorDiagnosticsResponse,
  type SkillRemediationAction,
} from '@/services/skill';

const CuratorSettingsPanel = memo(
  ({ className, onSweepComplete }: { className?: string; onSweepComplete?: () => void }) => {
    const t = useTranslations('settings.skills.curator');
    const tCommon = useTranslations('common');
    const baseId = useId();
    const titleId = `${baseId}-title`;
    const protectInstalledId = `${baseId}-protect-installed`;
    const consolidationTitleId = `${baseId}-consolidation-title`;
    const [config, setConfig] = useState<CuratorConfigResponse | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isRunning, setIsRunning] = useState(false);
    const [isDirty, setIsDirty] = useState(false);
    const [history, setHistory] = useState<CuratorHistoryEntry[]>([]);
    const [historyOpen, setHistoryOpen] = useState(false);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [isPreviewing, setIsPreviewing] = useState(false);
    const [isExecuting, setIsExecuting] = useState(false);
    const [preview, setPreview] = useState<ConsolidationPreviewResponse | null>(null);
    const [diagnostics, setDiagnostics] = useState<SkillDoctorDiagnosticsResponse | null>(null);
    const [diagLoading, setDiagLoading] = useState(false);
    const [remediatingSkill, setRemediatingSkill] = useState<string | null>(null);
    const [recorderOpen, setRecorderOpen] = useState(false);

    const loadDiagnostics = useCallback(async () => {
      setDiagLoading(true);
      try {
        const diag = await getSkillDiagnostics();
        setDiagnostics(diag);
      } catch {
        setDiagnostics(null);
      } finally {
        setDiagLoading(false);
      }
    }, []);

    useEffect(() => {
      getCuratorConfig()
        .then((c) => {
          setConfig(c);
          setIsLoading(false);
        })
        .catch(() => setIsLoading(false));

      loadDiagnostics();
    }, [loadDiagnostics]);

    const handleRemediate = useCallback(
      async (skillName: string, action: SkillRemediationAction) => {
        setRemediatingSkill(skillName);
        try {
          const res = await remediateSkillFinding(skillName, action);
          if (res.success) {
            toast({
              title: t('doctor.remediateSuccessTitle'),
              description: t('doctor.remediateSuccessDesc', { name: skillName }),
            });
            await loadDiagnostics();
            onSweepComplete?.();
          } else {
            toast({
              title: t('doctor.remediateFailedTitle'),
              description: res.error || t('doctor.remediateFailedDesc'),
              variant: 'destructive',
            });
          }
        } catch (err: unknown) {
          toast({
            title: t('doctor.remediateFailedTitle'),
            description: err instanceof Error ? err.message : t('doctor.remediateFailedDesc'),
            variant: 'destructive',
          });
        } finally {
          setRemediatingSkill(null);
        }
      },
      [t, loadDiagnostics, onSweepComplete],
    );

    const handleSave = useCallback(async () => {
      if (!config) {
        return;
      }
      try {
        const updated = await updateCuratorConfig(config);
        setConfig(updated);
        setIsDirty(false);
        toast({ title: t('configSaved') });
      } catch {
        toast({ title: t('configSaveFailed'), variant: 'destructive' });
      }
    }, [config, t]);

    const loadHistory = useCallback(async () => {
      setHistoryLoading(true);
      try {
        const entries = await getCuratorHistory(10);
        setHistory(entries);
      } catch {
        setHistory([]);
      } finally {
        setHistoryLoading(false);
      }
    }, []);

    const handleRunNow = useCallback(async () => {
      setIsRunning(true);
      try {
        const result = await runCuratorSweep();
        if (result.total_transitions > 0) {
          toast({
            title: t('runSuccess'),
            description: t('runResult', {
              scanned: result.skills_scanned,
              stale: result.stale_count,
              archived: result.archived_count,
            }),
          });
          onSweepComplete?.();
        } else {
          toast({ title: t('noChanges') });
        }
        if (historyOpen) {
          loadHistory();
        }
      } catch {
        toast({ title: t('configSaveFailed'), variant: 'destructive' });
      } finally {
        setIsRunning(false);
      }
    }, [t, onSweepComplete, historyOpen, loadHistory]);

    const toggleHistory = useCallback(() => {
      const next = !historyOpen;
      setHistoryOpen(next);
      if (next && history.length === 0) {
        loadHistory();
      }
    }, [historyOpen, history.length, loadHistory]);

    const updateField = useCallback(
      <K extends keyof CuratorConfigResponse>(key: K, value: CuratorConfigResponse[K]) => {
        setConfig((prev) => (prev ? { ...prev, [key]: value } : prev));
        setIsDirty(true);
      },
      [],
    );

    const handlePreview = useCallback(async () => {
      if (isDirty) {
        await handleSave();
      }
      setIsPreviewing(true);
      setPreview(null);
      try {
        const plan = await getConsolidationPreview();
        setPreview(plan);
        if (plan.actions.length === 0) {
          toast({ title: t('consolidation.emptyPlan') });
        }
      } catch {
        toast({ title: t('consolidation.executeFailed'), variant: 'destructive' });
      } finally {
        setIsPreviewing(false);
      }
    }, [t, isDirty, handleSave]);

    const handleExecute = useCallback(async () => {
      setIsExecuting(true);
      try {
        const result: ConsolidationExecuteResponse = await executeConsolidation();
        toast({
          title: t('consolidation.executeSuccess'),
          description: t('consolidation.executeResult', {
            archived: result.total_archived,
            created: result.total_created,
            agents: result.agent_refs_updated,
          }),
        });
        setPreview(null);
        onSweepComplete?.();
      } catch {
        toast({ title: t('consolidation.executeFailed'), variant: 'destructive' });
      } finally {
        setIsExecuting(false);
      }
    }, [t, onSweepComplete]);

    if (isLoading || !config) {
      return null;
    }

    return (
      <div className={className} data-testid="curator-panel">
        <div className="space-y-5">
          {diagnostics && (
            <CuratorDiagnosticsSection
              diagnostics={diagnostics}
              remediatingSkill={remediatingSkill}
              onRemediate={handleRemediate}
            />
          )}

          <div className="flex items-center justify-between">
            <div>
              <h4 id={titleId} className="text-sm font-medium">
                {t('title')}
              </h4>
              <p className="text-xs text-muted-foreground mt-0.5">{t('description')}</p>
              <p className="text-[11px] text-emerald-600 dark:text-emerald-500 mt-1.5 font-medium">
                {t('safetyPromise')}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setRecorderOpen(true)}
                className="h-8 gap-1.5 text-xs font-medium"
              >
                <Video className="h-3.5 w-3.5 text-primary" />
                <span>{t('recordWorkflowBtn')}</span>
              </Button>
              <Switch
                aria-labelledby={titleId}
                checked={config.enabled}
                onCheckedChange={(v) => updateField('enabled', v)}
              />
            </div>
          </div>

          <WorkflowRecorderModal
            isOpen={recorderOpen}
            onClose={() => setRecorderOpen(false)}
            onPublished={() => {
              loadDiagnostics();
              onSweepComplete?.();
            }}
          />

          {config.enabled && (
            <div className="space-y-4 pl-1">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <CuratorNumberField
                  label={t('staleAfterDays')}
                  description={t('staleAfterDaysDesc')}
                  min={1}
                  value={config.stale_after_days}
                  onCommit={(v) => updateField('stale_after_days', v)}
                />
                <CuratorNumberField
                  label={t('archiveAfterDays')}
                  description={t('archiveAfterDaysDesc')}
                  min={1}
                  value={config.archive_after_days}
                  onCommit={(v) => updateField('archive_after_days', v)}
                />
                <CuratorNumberField
                  label={t('gracePeriodDays')}
                  description={t('gracePeriodDaysDesc')}
                  min={0}
                  value={config.grace_period_days}
                  onCommit={(v) => updateField('grace_period_days', v)}
                />
                <CuratorNumberField
                  label={t('intervalHours')}
                  min={1}
                  value={config.interval_hours}
                  onCommit={(v) => updateField('interval_hours', v)}
                />
                <CuratorNumberField
                  label={t('maxSkills')}
                  description={t('maxSkillsDesc')}
                  min={5}
                  value={config.max_skills}
                  onCommit={(v) => updateField('max_skills', v)}
                />
              </div>

              <div className="flex items-center justify-between py-1">
                <div>
                  <Label htmlFor={protectInstalledId} className="text-xs">
                    {t('protectInstalled')}
                  </Label>
                  <p className="text-[11px] text-muted-foreground">{t('protectInstalledDesc')}</p>
                </div>
                <Switch
                  id={protectInstalledId}
                  checked={config.protect_installed_skills}
                  onCheckedChange={(v) => updateField('protect_installed_skills', v)}
                />
              </div>

              <div className="flex items-center gap-2 pt-2">
                <Button variant="outline" size="sm" onClick={handleRunNow} disabled={isRunning} className="gap-1.5">
                  {isRunning ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                  {isRunning ? t('running') : t('runNow')}
                </Button>
              </div>
            </div>
          )}

          <CuratorHistorySection
            open={historyOpen}
            loading={historyLoading}
            entries={history}
            onToggle={toggleHistory}
          />

          {/* Consolidation (Umbrella Merge) Section */}
          <div className="pt-3 border-t">
            <div className="flex items-center justify-between">
              <div>
                <h4 id={consolidationTitleId} className="text-sm font-medium flex items-center gap-1.5">
                  <Combine size={14} />
                  {t('consolidation.title')}
                </h4>
                <p className="text-xs text-muted-foreground mt-0.5">{t('consolidation.description')}</p>
              </div>
              <Switch
                aria-labelledby={consolidationTitleId}
                checked={config.consolidation_enabled}
                onCheckedChange={(v) => updateField('consolidation_enabled', v)}
              />
            </div>

            {config.consolidation_enabled && (
              <div className="mt-3 space-y-3 pl-1">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <CuratorNumberField
                    label={t('consolidation.minClusterSize')}
                    description={t('consolidation.minClusterSizeDesc')}
                    min={2}
                    max={10}
                    value={config.consolidation_min_cluster_size}
                    onCommit={(v) => updateField('consolidation_min_cluster_size', v)}
                  />
                  <CuratorNumberField
                    label={t('consolidation.similarityThreshold')}
                    description={t('consolidation.similarityThresholdDesc')}
                    min={0.5}
                    max={0.95}
                    step={0.05}
                    value={config.consolidation_similarity_threshold}
                    onCommit={(v) => updateField('consolidation_similarity_threshold', v)}
                  />
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handlePreview}
                    disabled={isPreviewing || isExecuting}
                    className="gap-1.5"
                  >
                    {isPreviewing ? <Loader2 size={14} className="animate-spin" /> : <Combine size={14} />}
                    {isPreviewing ? t('consolidation.previewing') : t('consolidation.preview')}
                  </Button>
                </div>

                {preview && preview.actions.length > 0 && (
                  <div className="mt-3 space-y-2 rounded-lg border p-3">
                    <div className="flex items-center justify-between">
                      <h5 className="text-xs font-medium">{t('consolidation.planTitle')}</h5>
                      <Badge variant="secondary" className="text-[10px]">
                        {t('consolidation.planSummary', {
                          affected: preview.total_skills_affected,
                          reduction: preview.estimated_reduction,
                        })}
                      </Badge>
                    </div>
                    <div className="space-y-1.5 max-h-48 overflow-y-auto">
                      {preview.actions.map((action, i) => (
                        <div key={i} className="text-xs border-l-2 border-primary/40 pl-2 py-1">
                          <div className="flex items-center gap-1.5">
                            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                              {action.action_type === 'merge'
                                ? t('consolidation.actionMerge')
                                : action.action_type === 'create_umbrella'
                                  ? t('consolidation.actionCreate')
                                  : t('consolidation.actionDemote')}
                            </Badge>
                            <span className="font-medium">{action.target_skill}</span>
                          </div>
                          <p className="text-muted-foreground mt-0.5">
                            {action.source_skills.join(', ')} → {action.target_skill}
                          </p>
                          <p className="text-muted-foreground opacity-70 mt-0.5">{action.reasoning}</p>
                        </div>
                      ))}
                    </div>
                    <ConfirmDialog
                      title={t('consolidation.confirmTitle')}
                      description={t('consolidation.confirmDesc', { count: preview.total_skills_affected })}
                      confirmText={t('consolidation.execute')}
                      cancelText={tCommon('cancel')}
                      variant="warning"
                      onConfirm={handleExecute}
                      trigger={
                        <Button size="sm" disabled={isExecuting} className="gap-1.5 mt-2">
                          {isExecuting ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                          {isExecuting ? t('consolidation.executing') : t('consolidation.execute')}
                        </Button>
                      }
                    />
                  </div>
                )}
              </div>
            )}
          </div>

          {isDirty && (
            <div className="sticky bottom-0 z-10 flex justify-end border-t bg-card/95 py-3 backdrop-blur">
              <Button size="sm" onClick={handleSave}>
                {t('save')}
              </Button>
            </div>
          )}
        </div>
      </div>
    );
  },
);

CuratorSettingsPanel.displayName = 'CuratorSettingsPanel';

export default CuratorSettingsPanel;
