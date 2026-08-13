'use client';

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Download, Loader2, Play, RefreshCw, Trash2, Upload } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import {
  deleteWorkflowTemplate,
  fetchWorkflowTemplateDetail,
  fetchWorkflowTemplates,
  type WorkflowTemplateSummary,
} from '@/services/workflowTemplates';
import { useWorkflowTemplateTransfer } from '@/lib/workflow/useWorkflowTemplateTransfer';
import { submitWorkflowTemplateRun } from '@/lib/workflow/submitWorkflowTemplateRun';
import { useToast } from '@/hooks/shared/useToast';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import WorkflowTemplateScriptPreview from './WorkflowTemplateScriptPreview';
import WorkflowTemplateArgsDialog from './WorkflowTemplateArgsDialog';

interface WorkflowTemplateLibrarySectionProps {
  className?: string;
}

const WorkflowTemplateLibrarySection = memo(({ className }: WorkflowTemplateLibrarySectionProps) => {
  const t = useTranslations('settings.skills.workflowTemplates');
  const router = useRouter();
  const { toast } = useToast();
  const [templates, setTemplates] = useState<WorkflowTemplateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runQuery, setRunQuery] = useState('');
  const [runningTemplateId, setRunningTemplateId] = useState<string | null>(null);
  const [argsDialogOpen, setArgsDialogOpen] = useState(false);
  const [pendingRunTemplate, setPendingRunTemplate] = useState<WorkflowTemplateSummary | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WorkflowTemplateSummary | null>(null);
  const [deleteBoundCronCount, setDeleteBoundCronCount] = useState(0);
  const [deleteDetailLoading, setDeleteDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchWorkflowTemplates();
      setTemplates(response.templates);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const {
    importInputRef,
    exportingTemplateId,
    importing,
    importOverwriteTarget,
    handleExport,
    handleImportInputChange,
    openImportPicker,
    dismissImportOverwrite,
    confirmImportOverwrite,
  } = useWorkflowTemplateTransfer({
    templates,
    reloadTemplates: load,
    toast,
  });

  const sortedTemplates = useMemo(
    () => [...templates].sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    [templates],
  );

  const executeRun = useCallback(
    async (template: WorkflowTemplateSummary, templateArgs?: Record<string, string>) => {
      const query = runQuery.trim();
      if (!query) {
        toast({ title: t('runQueryRequired'), variant: 'destructive' });
        return;
      }
      setRunningTemplateId(template.template_id);
      try {
        const result = await submitWorkflowTemplateRun({
          templateId: template.template_id,
          displayName: template.display_name,
          query,
          templateArgs: templateArgs ?? null,
        });
        if (result.ok) {
          toast({ title: t('runStarted'), description: t('runStartedHint') });
          router.push(`/${result.chatId}`);
          return;
        }
        if (result.reason === 'busy') {
          toast({ title: t('runBusy'), variant: 'destructive' });
          return;
        }
        if (result.reason === 'no_chat') {
          toast({ title: t('runNoChat'), variant: 'destructive' });
          return;
        }
        toast({ title: t('runFailed'), variant: 'destructive' });
      } finally {
        setRunningTemplateId(null);
      }
    },
    [runQuery, router, t, toast],
  );

  const handleRun = useCallback(
    (template: WorkflowTemplateSummary) => {
      const query = runQuery.trim();
      if (!query) {
        toast({ title: t('runQueryRequired'), variant: 'destructive' });
        return;
      }
      if (template.placeholders.length > 0) {
        setPendingRunTemplate(template);
        setArgsDialogOpen(true);
        return;
      }
      void executeRun(template);
    },
    [executeRun, runQuery, t, toast],
  );

  const handleDeleteRequest = useCallback(
    async (template: WorkflowTemplateSummary) => {
      setDeleteDetailLoading(true);
      try {
        const detail = await fetchWorkflowTemplateDetail(template.template_id);
        setDeleteBoundCronCount(detail.bound_cron_count);
        setDeleteTarget(template);
      } catch (err) {
        toast({
          title: t('deleteFailed'),
          description: err instanceof Error ? err.message : undefined,
          variant: 'destructive',
        });
      } finally {
        setDeleteDetailLoading(false);
      }
    },
    [t, toast],
  );

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) {return;}
    const templateId = deleteTarget.template_id;
    try {
      await deleteWorkflowTemplate(templateId);
      setTemplates((prev) => prev.filter((item) => item.template_id !== templateId));
      toast({ title: t('deleted') });
      setDeleteTarget(null);
      setDeleteBoundCronCount(0);
    } catch (err) {
      toast({
        title: t('deleteFailed'),
        description: err instanceof Error ? err.message : undefined,
        variant: 'destructive',
      });
      throw err;
    }
  }, [deleteTarget, t, toast]);

  return (
    <div className={cn('space-y-5', className)} data-testid="workflow-template-library">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <Input
          value={runQuery}
          onChange={(event) => setRunQuery(event.target.value)}
          placeholder={t('runQueryPlaceholder')}
          className="max-w-xl"
        />
        <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading} className="gap-2 shrink-0">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {t('refresh')}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="gap-2 shrink-0"
          disabled={importing}
          onClick={openImportPicker}
        >
          {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {t('import')}
        </Button>
        <input
          ref={importInputRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={handleImportInputChange}
        />
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t('loading')}
        </div>
      )}

      {!loading && error && <p className="text-sm text-destructive">{error}</p>}

      {!loading && !error && sortedTemplates.length === 0 && (
        <p className="text-sm text-muted-foreground">{t('empty')}</p>
      )}

      <div className="space-y-3">
        {sortedTemplates.map((template) => (
          <div
            key={template.template_id}
            className="rounded-xl border border-border/50 bg-card/60 px-4 py-3 flex flex-col sm:flex-row sm:items-start gap-3"
          >
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground">{template.display_name}</p>
              <p className="text-xs text-muted-foreground mt-0.5">{template.template_id}</p>
              {template.required_agent_types.length > 0 && (
                <p className="text-[11px] text-muted-foreground/80 mt-1">
                  {t('agentTypes', { types: template.required_agent_types.join(', ') })}
                </p>
              )}
              {template.placeholders.length > 0 && (
                <p className="text-[11px] text-muted-foreground/80 mt-1">
                  {t('placeholdersHint', { keys: template.placeholders.join(', ') })}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-2 mt-2">
                {template.trust_latch ? (
                  <Badge variant="secondary" className="text-[10px] uppercase tracking-wide">
                    {t('trustLatchOn')}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[10px] uppercase tracking-wide">
                    {t('trustLatchOff')}
                  </Badge>
                )}
              </div>
              <WorkflowTemplateScriptPreview templateId={template.template_id} />
            </div>
            <div className="flex flex-wrap items-center gap-2 shrink-0 sm:pt-0.5">
              <Button
                size="sm"
                className="gap-1.5"
                onClick={() => handleRun(template)}
                disabled={runningTemplateId === template.template_id}
              >
                {runningTemplateId === template.template_id ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Play className="h-3.5 w-3.5" />
                )}
                {t('run')}
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
                onClick={() => void handleExport(template)}
                disabled={exportingTemplateId === template.template_id}
              >
                {exportingTemplateId === template.template_id ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Download className="h-3.5 w-3.5" />
                )}
                {t('export')}
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5 text-destructive hover:text-destructive"
                onClick={() => void handleDeleteRequest(template)}
                disabled={deleteDetailLoading && deleteTarget?.template_id === template.template_id}
              >
                <Trash2 className="h-3.5 w-3.5" />
                {t('delete')}
              </Button>
            </div>
          </div>
        ))}
      </div>

      {pendingRunTemplate ? (
        <WorkflowTemplateArgsDialog
          open={argsDialogOpen}
          templateName={pendingRunTemplate.display_name}
          placeholders={pendingRunTemplate.placeholders}
          onOpenChange={(open) => {
            setArgsDialogOpen(open);
            if (!open) {
              setPendingRunTemplate(null);
            }
          }}
          onConfirm={(args) => {
            void executeRun(pendingRunTemplate, args);
            setPendingRunTemplate(null);
          }}
        />
      ) : null}

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTarget(null);
            setDeleteBoundCronCount(0);
          }
        }}
        title={t('deleteConfirmTitle')}
        description={
          deleteTarget
            ? deleteBoundCronCount > 0
              ? t('deleteConfirmWithCron', {
                  name: deleteTarget.display_name,
                  count: deleteBoundCronCount,
                })
              : t('deleteConfirm', { name: deleteTarget.display_name })
            : ''
        }
        confirmText={t('delete')}
        cancelText={t('deleteCancel')}
        variant="destructive"
        onConfirm={handleDeleteConfirm}
      />

      <ConfirmDialog
        open={!!importOverwriteTarget}
        onOpenChange={(open) => {
          if (!open) {
            dismissImportOverwrite();
          }
        }}
        title={t('importOverwriteTitle')}
        description={
          importOverwriteTarget
            ? t('importOverwriteConfirm', { name: importOverwriteTarget.displayName })
            : ''
        }
        confirmText={t('importOverwriteAction')}
        cancelText={t('deleteCancel')}
        variant="destructive"
        onConfirm={confirmImportOverwrite}
      />
    </div>
  );
});

WorkflowTemplateLibrarySection.displayName = 'WorkflowTemplateLibrarySection';

export default WorkflowTemplateLibrarySection;
