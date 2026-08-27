'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  Play,
  Loader2,
  History,
  ChevronDown,
  ChevronRight,
  Combine,
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  RotateCcw,
  Archive,
  Video,
} from 'lucide-react';
import { WorkflowRecorderModal } from './WorkflowRecorderModal';
import { Switch } from '@/components/primitives/switch';
import { Label } from '@/components/primitives/label';
import { Input } from '@/components/primitives/input';
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
  type SkillDoctorFindingItem,
} from '@/services/skill';

function formatRelativeTime(isoTimestamp: string): string {
  const diff = Date.now() - new Date(isoTimestamp).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) {
    return '<1m ago';
  }
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

const CuratorSettingsPanel = memo(
  ({ className, onSweepComplete }: { className?: string; onSweepComplete?: () => void }) => {
    const t = useTranslations('settings.skills.curator');
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
      async (skillName: string, action: 'unpin_and_archive' | 'archive' | 'reset_stats') => {
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
      <div className={className}>
        <div className="space-y-5">
          {/* Skill Health Doctor Diagnostics Section */}
          {diagnostics && (
            <div
              className={`p-3.5 rounded-lg border transition-all ${
                diagnostics.findings.length > 0
                  ? 'bg-amber-500/5 dark:bg-amber-500/10 border-amber-500/30'
                  : 'bg-emerald-500/5 dark:bg-emerald-500/10 border-emerald-500/20'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  {diagnostics.findings.length > 0 ? (
                    <ShieldAlert className="h-4 w-4 text-amber-500" />
                  ) : (
                    <ShieldCheck className="h-4 w-4 text-emerald-500" />
                  )}
                  <span className="text-xs font-semibold">
                    {diagnostics.findings.length > 0
                      ? t('doctor.titleAttention', { count: diagnostics.findings.length })
                      : t('doctor.titleHealthy')}
                  </span>
                </div>
                <Badge
                  variant="outline"
                  className={`text-[11px] font-mono px-2 py-0.5 ${
                    diagnostics.health_score >= 85
                      ? 'border-emerald-500/30 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10'
                      : 'border-amber-500/30 text-amber-600 dark:text-amber-400 bg-amber-500/10'
                  }`}
                >
                  Score: {diagnostics.health_score}/100
                </Badge>
              </div>

              {diagnostics.findings.length === 0 ? (
                <p className="text-xs text-muted-foreground">{t('doctor.allHealthyDesc')}</p>
              ) : (
                <div className="space-y-2 mt-2.5">
                  {diagnostics.findings.map((f, idx) => (
                    <div
                      key={`${f.skill_name}-${idx}`}
                      className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-2.5 rounded bg-background/60 border border-border/60 text-xs"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="font-medium text-foreground">{f.skill_name}</span>
                          {f.pinned && (
                            <Badge variant="secondary" className="text-[10px] h-4 px-1.5 bg-muted">
                              PINNED
                            </Badge>
                          )}
                          <Badge
                            variant="outline"
                            className={`text-[10px] h-4 px-1.5 ${
                              f.severity === 'critical'
                                ? 'border-destructive/40 text-destructive bg-destructive/10'
                                : 'border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-500/10'
                            }`}
                          >
                            {f.finding_type === 'wrong_but_frequent'
                              ? t('doctor.typeWrongButFrequent')
                              : f.finding_type === 'hoarding_bloat'
                                ? t('doctor.typeHoarding')
                                : t('doctor.typeStalePinned')}
                          </Badge>
                        </div>
                        <p className="text-[11px] text-muted-foreground">{f.message}</p>
                      </div>

                      {f.skill_name !== '[Library Bloat]' && (
                        <div className="flex items-center gap-1.5 shrink-0">
                          {f.pinned && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={remediatingSkill === f.skill_name}
                              onClick={() => handleRemediate(f.skill_name, 'unpin_and_archive')}
                              className="h-6 px-2 text-[11px] gap-1 border-amber-500/30 hover:bg-amber-500/10"
                            >
                              {remediatingSkill === f.skill_name ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <Archive className="h-3 w-3 text-amber-500" />
                              )}
                              <span>{t('doctor.actionUnpinArchive')}</span>
                            </Button>
                          )}
                          {!f.pinned && f.finding_type === 'wrong_but_frequent' && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={remediatingSkill === f.skill_name}
                              onClick={() => handleRemediate(f.skill_name, 'archive')}
                              className="h-6 px-2 text-[11px] gap-1 border-amber-500/30 hover:bg-amber-500/10"
                            >
                              {remediatingSkill === f.skill_name ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <Archive className="h-3 w-3 text-amber-500" />
                              )}
                              <span>{t('doctor.actionArchive')}</span>
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="ghost"
                            disabled={remediatingSkill === f.skill_name}
                            onClick={() => handleRemediate(f.skill_name, 'reset_stats')}
                            className="h-6 px-2 text-[11px] gap-1 text-muted-foreground hover:text-foreground"
                            title={t('doctor.actionResetTooltip')}
                          >
                            <RotateCcw className="h-3 w-3" />
                            <span>{t('doctor.actionReset')}</span>
                          </Button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-medium">{t('title')}</h4>
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
              <Switch checked={config.enabled} onCheckedChange={(v) => updateField('enabled', v)} />
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
                <div className="space-y-1.5">
                  <Label className="text-xs">{t('staleAfterDays')}</Label>
                  <Input
                    type="number"
                    min={1}
                    value={config.stale_after_days}
                    onChange={(e) => updateField('stale_after_days', Number(e.target.value))}
                    className="h-8"
                  />
                  <p className="text-[11px] text-muted-foreground">{t('staleAfterDaysDesc')}</p>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs">{t('archiveAfterDays')}</Label>
                  <Input
                    type="number"
                    min={1}
                    value={config.archive_after_days}
                    onChange={(e) => updateField('archive_after_days', Number(e.target.value))}
                    className="h-8"
                  />
                  <p className="text-[11px] text-muted-foreground">{t('archiveAfterDaysDesc')}</p>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs">{t('gracePeriodDays')}</Label>
                  <Input
                    type="number"
                    min={0}
                    value={config.grace_period_days}
                    onChange={(e) => updateField('grace_period_days', Number(e.target.value))}
                    className="h-8"
                  />
                  <p className="text-[11px] text-muted-foreground">{t('gracePeriodDaysDesc')}</p>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs">{t('intervalHours')}</Label>
                  <Input
                    type="number"
                    min={1}
                    value={config.interval_hours}
                    onChange={(e) => updateField('interval_hours', Number(e.target.value))}
                    className="h-8"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs">{t('maxSkills')}</Label>
                  <Input
                    type="number"
                    min={5}
                    value={config.max_skills}
                    onChange={(e) => updateField('max_skills', Number(e.target.value))}
                    className="h-8"
                  />
                  <p className="text-[11px] text-muted-foreground">{t('maxSkillsDesc')}</p>
                </div>
              </div>

              <div className="flex items-center justify-between py-1">
                <div>
                  <Label className="text-xs">{t('protectInstalled')}</Label>
                  <p className="text-[11px] text-muted-foreground">{t('protectInstalledDesc')}</p>
                </div>
                <Switch
                  checked={config.protect_installed_skills}
                  onCheckedChange={(v) => updateField('protect_installed_skills', v)}
                />
              </div>

              <div className="flex items-center gap-2 pt-2">
                {isDirty && (
                  <Button size="sm" onClick={handleSave}>
                    {t('save')}
                  </Button>
                )}
                <Button variant="outline" size="sm" onClick={handleRunNow} disabled={isRunning} className="gap-1.5">
                  {isRunning ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                  {isRunning ? t('running') : t('runNow')}
                </Button>
              </div>
            </div>
          )}

          {/* Recent Runs History — always visible regardless of enabled state */}
          <div className="pt-3 border-t">
            <button
              type="button"
              onClick={toggleHistory}
              className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              {historyOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              <History size={12} />
              {t('recentRuns')}
            </button>

            {historyOpen && (
              <div className="mt-2 space-y-2">
                {historyLoading ? (
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground py-2">
                    <Loader2 size={12} className="animate-spin" />
                    {t('loadingHistory')}
                  </div>
                ) : history.length === 0 ? (
                  <p className="text-xs text-muted-foreground py-2">{t('noHistory')}</p>
                ) : (
                  history.map((entry, idx) => (
                    <div key={`${entry.timestamp}-${idx}`} className="rounded-full border px-3 py-2 text-xs space-y-1">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground">{formatRelativeTime(entry.timestamp)}</span>
                          <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                            {entry.trigger === 'manual' ? t('triggerManual') : t('triggerBackground')}
                          </Badge>
                        </div>
                        <span className="text-muted-foreground">{entry.duration_ms}ms</span>
                      </div>
                      <div className="flex items-center gap-3 text-muted-foreground">
                        <span>{t('historyScanned', { count: entry.skills_scanned })}</span>
                        {entry.total_transitions > 0 && (
                          <>
                            {entry.stale_count > 0 && (
                              <span className="text-yellow-600 dark:text-yellow-500">{entry.stale_count} stale</span>
                            )}
                            {entry.archived_count > 0 && (
                              <span className="text-red-600 dark:text-red-400">{entry.archived_count} archived</span>
                            )}
                          </>
                        )}
                        {entry.total_transitions === 0 && (
                          <span className="text-green-600 dark:text-green-400">{t('noChanges')}</span>
                        )}
                      </div>
                      {entry.transitions.length > 0 && (
                        <div className="pt-1 space-y-0.5">
                          {entry.transitions.map((tr, i) => (
                            <div key={i} className="text-[11px] text-muted-foreground pl-2 border-l-2 border-muted">
                              <span className="font-medium text-foreground">{tr.skill_name}</span> {tr.from_status} →{' '}
                              {tr.to_status}
                              <span className="ml-1 opacity-60">({tr.reason})</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Consolidation (Umbrella Merge) Section */}
          <div className="pt-3 border-t">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-sm font-medium flex items-center gap-1.5">
                  <Combine size={14} />
                  {t('consolidation.title')}
                </h4>
                <p className="text-xs text-muted-foreground mt-0.5">{t('consolidation.description')}</p>
              </div>
              <Switch
                checked={config.consolidation_enabled}
                onCheckedChange={(v) => updateField('consolidation_enabled', v)}
              />
            </div>

            {config.consolidation_enabled && (
              <div className="mt-3 space-y-3 pl-1">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label className="text-xs">{t('consolidation.minClusterSize')}</Label>
                    <Input
                      type="number"
                      min={2}
                      max={10}
                      value={config.consolidation_min_cluster_size}
                      onChange={(e) => updateField('consolidation_min_cluster_size', Number(e.target.value))}
                      className="h-8"
                    />
                    <p className="text-[11px] text-muted-foreground">{t('consolidation.minClusterSizeDesc')}</p>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">{t('consolidation.similarityThreshold')}</Label>
                    <Input
                      type="number"
                      min={0.5}
                      max={0.95}
                      step={0.05}
                      value={config.consolidation_similarity_threshold}
                      onChange={(e) => updateField('consolidation_similarity_threshold', Number(e.target.value))}
                      className="h-8"
                    />
                    <p className="text-[11px] text-muted-foreground">{t('consolidation.similarityThresholdDesc')}</p>
                  </div>
                </div>

                <div className="flex items-center gap-2 pt-1">
                  {isDirty && (
                    <Button size="sm" onClick={handleSave}>
                      {t('save')}
                    </Button>
                  )}
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
                      cancelText={t('save')}
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
        </div>
      </div>
    );
  },
);

CuratorSettingsPanel.displayName = 'CuratorSettingsPanel';

export default CuratorSettingsPanel;
