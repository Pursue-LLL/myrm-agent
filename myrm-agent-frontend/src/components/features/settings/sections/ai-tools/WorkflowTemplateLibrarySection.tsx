'use client';

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Loader2, Play, RefreshCw, Trash2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import {
  deleteWorkflowTemplate,
  fetchWorkflowTemplates,
  type WorkflowTemplateSummary,
} from '@/services/workflowTemplates';
import { submitWorkflowTemplateRun } from '@/lib/workflow/submitWorkflowTemplateRun';
import { useToast } from '@/hooks/shared/useToast';
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

  const handleDelete = useCallback(
    async (templateId: string) => {
      try {
        await deleteWorkflowTemplate(templateId);
        setTemplates((prev) => prev.filter((item) => item.template_id !== templateId));
        toast({ title: t('deleted') });
      } catch (err) {
        toast({
          title: t('deleteFailed'),
          description: err instanceof Error ? err.message : undefined,
          variant: 'destructive',
        });
      }
    },
    [t, toast],
  );

  return (
    <div className={cn('space-y-5', className)}>
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
            <div className="flex items-center gap-2 shrink-0 sm:pt-0.5">
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
                className="gap-1.5 text-destructive hover:text-destructive"
                onClick={() => void handleDelete(template.template_id)}
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
    </div>
  );
});

WorkflowTemplateLibrarySection.displayName = 'WorkflowTemplateLibrarySection';

export default WorkflowTemplateLibrarySection;
