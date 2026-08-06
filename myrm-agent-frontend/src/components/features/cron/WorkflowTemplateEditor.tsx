'use client';

/**
 * [INPUT]
 * @/services/cron::updateCronJob (POS: Frontend Cron API client)
 * @/services/workflowTemplates::fetchWorkflowTemplates (POS: Workflow template list API)
 * ../settings/sections/ai-tools/WorkflowTemplateArgsDialog (POS: placeholder args modal)
 * ./CronDeliveryEditors::EditorProps (POS: Cron per-job editor shared props)
 *
 * [OUTPUT]
 * WorkflowTemplateEditor: edit Cron job workflow template binding and args via PATCH;
 * missing-template amber warning with unbind; invalid binding follows server display_name.
 *
 * [POS]
 * CronRunHistory per-job editor. Mirrors create-dialog trust-latch template picker.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, Route, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Label } from '@/components/primitives/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives/select';
import { updateCronJob } from '@/services/cron';
import {
  fetchWorkflowTemplates,
  type WorkflowTemplateSummary,
} from '@/services/workflowTemplates';
import WorkflowTemplateArgsDialog from '@/components/features/settings/sections/ai-tools/WorkflowTemplateArgsDialog';
import type { EditorProps } from './CronDeliveryEditors';

function normalizeTemplateId(templateId: string | null | undefined): string {
  return templateId?.trim() || '__none__';
}

function argsEqual(
  left: Record<string, string> | null | undefined,
  right: Record<string, string> | null | undefined,
): boolean {
  const a = left ?? {};
  const b = right ?? {};
  const aKeys = Object.keys(a).sort();
  const bKeys = Object.keys(b).sort();
  if (aKeys.length !== bKeys.length) return false;
  return aKeys.every((key) => (a[key] ?? '').trim() === (b[key] ?? '').trim());
}

export function WorkflowTemplateEditor({ job, onUpdated }: EditorProps) {
  const t = useTranslations('cron');
  const [templates, setTemplates] = useState<WorkflowTemplateSummary[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(true);
  const [templateId, setTemplateId] = useState(() => normalizeTemplateId(job.workflow_template_id));
  const [templateArgs, setTemplateArgs] = useState<Record<string, string> | null>(
    job.workflow_template_args ?? null,
  );
  const [argsDialogOpen, setArgsDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [templatesLoadFailed, setTemplatesLoadFailed] = useState(false);

  useEffect(() => {
    setTemplateId(normalizeTemplateId(job.workflow_template_id));
    setTemplateArgs(job.workflow_template_args ?? null);
  }, [job.workflow_template_args, job.workflow_template_id]);

  const loadTemplates = useCallback(() => {
    let cancelled = false;
    setLoadingTemplates(true);
    setTemplatesLoadFailed(false);
    void fetchWorkflowTemplates()
      .then((response) => {
        if (!cancelled) {
          setTemplates(response.templates.filter((template) => template.trust_latch));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTemplates([]);
          setTemplatesLoadFailed(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingTemplates(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    return loadTemplates();
  }, [loadTemplates]);

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.template_id === templateId) ?? null,
    [templateId, templates],
  );

  const serverTemplateId = normalizeTemplateId(job.workflow_template_id);
  const serverBindingInvalid =
    serverTemplateId !== '__none__' && !job.workflow_template_display_name?.trim();

  const templateMissing = serverBindingInvalid && templateId === serverTemplateId;

  const dirty =
    templateId !== serverTemplateId ||
    !argsEqual(templateArgs, job.workflow_template_args);

  const persistBinding = useCallback(
    async (nextTemplateId: string, nextArgs: Record<string, string> | null) => {
      setSaving(true);
      try {
        if (nextTemplateId === '__none__') {
          await updateCronJob(job.id, {
            workflow_template_id: null,
            workflow_template_args: null,
          });
        } else {
          await updateCronJob(job.id, {
            workflow_template_id: nextTemplateId,
            ...(nextArgs && Object.keys(nextArgs).length > 0
              ? { workflow_template_args: nextArgs }
              : {}),
          });
        }
        onUpdated();
        toast.success(t('workflowTemplateUpdated'));
      } catch {
        toast.error(t('actionFail'));
      } finally {
        setSaving(false);
      }
    },
    [job.id, onUpdated, t],
  );

  const handleSave = useCallback(() => {
    if (templateId !== '__none__' && templateMissing && templateId === serverTemplateId) {
      return;
    }
    if (templateId !== '__none__' && !selectedTemplate && !templateMissing) {
      return;
    }
    if (
      templateId !== '__none__' &&
      selectedTemplate &&
      selectedTemplate.placeholders.length > 0 &&
      !templateArgs
    ) {
      setArgsDialogOpen(true);
      return;
    }
    void persistBinding(templateId, templateArgs);
  }, [persistBinding, selectedTemplate, templateArgs, templateId, templateMissing, serverTemplateId]);

  const handleUnbind = useCallback(async () => {
    const previousTemplateId = templateId;
    const previousTemplateArgs = templateArgs;
    setTemplateId('__none__');
    setTemplateArgs(null);
    setSaving(true);
    try {
      await updateCronJob(job.id, {
        workflow_template_id: null,
        workflow_template_args: null,
      });
      onUpdated();
      toast.success(t('workflowTemplateUpdated'));
    } catch {
      setTemplateId(previousTemplateId);
      setTemplateArgs(previousTemplateArgs);
      toast.error(t('actionFail'));
    } finally {
      setSaving(false);
    }
  }, [job.id, onUpdated, t, templateArgs, templateId]);

  const displayLabel =
    job.workflow_template_display_name?.trim() ||
    selectedTemplate?.display_name ||
    (templateMissing ? templateId : job.workflow_template_id?.trim() ?? '');

  return (
    <div className="rounded-lg border border-border/60 bg-card/60 px-4 py-3 space-y-3">
      <div className="flex items-center gap-1.5">
        <Route className="h-3.5 w-3.5 text-teal-600 dark:text-teal-400 shrink-0" />
        <span className="text-xs font-medium text-foreground">{t('workflowTemplateEditorTitle')}</span>
      </div>

      {displayLabel && templateId !== '__none__' && !templateMissing ? (
        <p className="text-sm text-foreground">{displayLabel}</p>
      ) : null}

      {templatesLoadFailed ? (
        <div className="flex flex-col gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-destructive">{t('workflowTemplateLoadFailed')}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="shrink-0 self-start"
            disabled={loadingTemplates}
            onClick={() => {
              loadTemplates();
            }}
          >
            {loadingTemplates ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : null}
            {t('workflowTemplateRetryLoad')}
          </Button>
        </div>
      ) : null}

      {templateMissing ? (
        <div className="flex flex-col gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2.5 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-2 min-w-0">
            <ShieldAlert className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            <div className="min-w-0 space-y-1">
              <p className="text-xs text-amber-700 dark:text-amber-400">
                {t('workflowTemplateMissingWarning')}
              </p>
              <p className="text-[11px] text-muted-foreground break-all font-mono">{templateId}</p>
            </div>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="shrink-0 self-start border-amber-500/30"
            disabled={saving}
            onClick={() => void handleUnbind()}
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : null}
            {t('workflowTemplateUnbind')}
          </Button>
        </div>
      ) : null}

      <div className="space-y-1.5">
        <Label className="text-xs">{t('createWorkflowTemplateLabel')}</Label>
        <Select
          value={templateId}
          onValueChange={(value) => {
            setTemplateId(value);
            setTemplateArgs(null);
            if (value !== '__none__') {
              const nextTemplate = templates.find((template) => template.template_id === value);
              if (nextTemplate && nextTemplate.placeholders.length > 0) {
                setArgsDialogOpen(true);
              }
            }
          }}
          disabled={loadingTemplates || saving}
        >
          <SelectTrigger className="h-8 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">{t('createWorkflowTemplateNone')}</SelectItem>
            {templateMissing ? (
              <SelectItem value={templateId} disabled>
                {displayLabel || templateId}
              </SelectItem>
            ) : null}
            {templates.map((template) => (
              <SelectItem key={template.template_id} value={template.template_id}>
                {template.display_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-[11px] text-muted-foreground">{t('workflowTemplateEditorHint')}</p>
      </div>

      {templateId !== '__none__' && templateArgs && Object.keys(templateArgs).length > 0 ? (
        <ul className="space-y-0.5">
          {Object.entries(templateArgs)
            .filter(([, value]) => value.trim().length > 0)
            .map(([key, value]) => (
              <li key={key} className="text-xs text-muted-foreground break-all">
                <span className="font-medium text-foreground/90">{key}</span>
                <span className="mx-1">=</span>
                <span>{value}</span>
              </li>
            ))}
        </ul>
      ) : null}

      {templateId !== '__none__' &&
      selectedTemplate &&
      selectedTemplate.placeholders.length > 0 ? (
        <div className="flex justify-start">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={saving}
            onClick={() => setArgsDialogOpen(true)}
          >
            {t('workflowTemplateEditArgs')}
          </Button>
        </div>
      ) : null}

      {dirty ? (
        <div className="flex justify-end">
          <Button size="sm" onClick={() => void handleSave()} disabled={saving}>
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : null}
            {t('workflowTemplateEditorSave')}
          </Button>
        </div>
      ) : null}

      {selectedTemplate ? (
        <WorkflowTemplateArgsDialog
          open={argsDialogOpen}
          templateName={selectedTemplate.display_name}
          placeholders={selectedTemplate.placeholders}
          onOpenChange={setArgsDialogOpen}
          initialArgs={templateArgs}
          onConfirm={(args) => {
            setTemplateArgs(args);
            setArgsDialogOpen(false);
            if (templateId !== serverTemplateId || !argsEqual(args, job.workflow_template_args)) {
              void persistBinding(templateId, args);
            }
          }}
        />
      ) : null}
    </div>
  );
}
