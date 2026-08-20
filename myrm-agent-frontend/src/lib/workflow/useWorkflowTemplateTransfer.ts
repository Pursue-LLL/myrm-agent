'use client';

import { useCallback, useRef, useState, type ChangeEvent } from 'react';
import { useTranslations } from 'next-intl';

import {
  buildWorkflowTemplateBundle,
  downloadWorkflowTemplateBundle,
  parseWorkflowTemplateBundle,
  workflowTemplateExportFilename,
  WORKFLOW_TEMPLATE_IMPORT_MAX_BYTES,
  type ParsedWorkflowTemplateImport,
} from '@/lib/workflow/workflowTemplateBundle';
import {
  fetchWorkflowTemplateDetail,
  upsertWorkflowTemplate,
  type WorkflowTemplateSummary,
} from '@/services/workflowTemplates';

interface UseWorkflowTemplateTransferOptions {
  templates: WorkflowTemplateSummary[];
  reloadTemplates: () => Promise<void>;
  toast: (options: { title: string; description?: string; variant?: 'default' | 'destructive' }) => void;
}

export function useWorkflowTemplateTransfer({ templates, reloadTemplates, toast }: UseWorkflowTemplateTransferOptions) {
  const t = useTranslations('settings.skills.workflowTemplates');
  const importInputRef = useRef<HTMLInputElement>(null);
  const [exportingTemplateId, setExportingTemplateId] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [importOverwriteTarget, setImportOverwriteTarget] = useState<ParsedWorkflowTemplateImport | null>(null);

  const handleExport = useCallback(
    async (template: WorkflowTemplateSummary) => {
      setExportingTemplateId(template.template_id);
      try {
        const detail = await fetchWorkflowTemplateDetail(template.template_id);
        const bundle = buildWorkflowTemplateBundle(detail);
        downloadWorkflowTemplateBundle(bundle, workflowTemplateExportFilename(template.template_id));
        toast({ title: t('exportSuccess'), description: t('exportSuccessHint') });
      } catch (err) {
        toast({
          title: t('exportFailed'),
          description: err instanceof Error ? err.message : undefined,
          variant: 'destructive',
        });
      } finally {
        setExportingTemplateId(null);
      }
    },
    [t, toast],
  );

  const commitImport = useCallback(
    async (payload: ParsedWorkflowTemplateImport) => {
      setImporting(true);
      try {
        await upsertWorkflowTemplate(payload.templateId, {
          display_name: payload.displayName,
          script_code: payload.scriptCode,
          trust_latch: payload.trustLatch,
        });
        await reloadTemplates();
        toast({
          title: t('importSuccess'),
          description: t('importSuccessHint'),
        });
        setImportOverwriteTarget(null);
      } catch (err) {
        toast({
          title: t('importFailed'),
          description: err instanceof Error ? err.message : undefined,
          variant: 'destructive',
        });
        throw err;
      } finally {
        setImporting(false);
      }
    },
    [reloadTemplates, t, toast],
  );

  const handleImportFile = useCallback(
    async (file: File) => {
      if (file.size > WORKFLOW_TEMPLATE_IMPORT_MAX_BYTES) {
        toast({ title: t('importFileTooLarge'), variant: 'destructive' });
        return;
      }

      const raw = await file.text();
      const parsed = parseWorkflowTemplateBundle(raw);
      if (!parsed.ok) {
        toast({ title: t('importInvalidFile'), variant: 'destructive' });
        return;
      }

      const exists = templates.some((item) => item.template_id === parsed.value.templateId);
      if (exists) {
        setImportOverwriteTarget(parsed.value);
        return;
      }

      try {
        await commitImport(parsed.value);
      } catch {
        // commitImport already surfaces importFailed toast
      }
    },
    [commitImport, t, templates, toast],
  );

  const handleImportInputChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = '';
      if (!file) {
        return;
      }
      void handleImportFile(file);
    },
    [handleImportFile],
  );

  const openImportPicker = useCallback(() => {
    importInputRef.current?.click();
  }, []);

  const dismissImportOverwrite = useCallback(() => {
    setImportOverwriteTarget(null);
  }, []);

  const confirmImportOverwrite = useCallback(async () => {
    if (!importOverwriteTarget) {
      return;
    }
    await commitImport(importOverwriteTarget);
  }, [commitImport, importOverwriteTarget]);

  return {
    importInputRef,
    exportingTemplateId,
    importing,
    importOverwriteTarget,
    handleExport,
    handleImportInputChange,
    openImportPicker,
    dismissImportOverwrite,
    confirmImportOverwrite,
  };
}
