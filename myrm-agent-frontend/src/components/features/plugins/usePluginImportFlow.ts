'use client';

import { useCallback, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';

import { resolveApiErrorDetail, resolveArchiveSecurityErrorI18nKey } from '@/services/archiveSecurityErrorCore';
import { toast } from '@/hooks/shared/useToast';
import useAgentStore from '@/store/useAgentStore';

import {
  bulkResolution,
  countSelected,
  defaultDecisions,
  type ComponentKind,
  type ImportDecisions,
  type PluginConfirmResult,
  type PluginPreviewPayload,
  type Resolution,
} from './pluginImportTypes';

const MAX_ARCHIVE_BYTES = 20 * 1024 * 1024;

interface ApiErrorPayload {
  detail?: unknown;
}

interface UsePluginImportFlowOptions {
  onOpenChange: (open: boolean) => void;
  onImportComplete: () => void;
}

/** Upload → preview → decide → confirm. The dialog only renders what this hook holds. */
export function usePluginImportFlow({ onOpenChange, onImportComplete }: UsePluginImportFlowOptions) {
  const t = useTranslations('settings.plugins.import');
  // Archive-security refusals share the wording of the skills import.
  const tArchive = useTranslations('settings.skills');
  const { agents, fetchAgents } = useAgentStore();

  const [isParsing, setIsParsing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PluginPreviewPayload | null>(null);
  const [decisions, setDecisions] = useState<ImportDecisions>({ skills: [], servers: [], agents: [] });
  const [bindAgentId, setBindAgentId] = useState<string | null>(null);
  const [trusted, setTrusted] = useState(false);
  const [result, setResult] = useState<PluginConfirmResult | null>(null);

  /**
   * Localized sentence for a refused request. Only the backend's stable archive-security codes have
   * wording of their own; every other backend sentence is an English diagnostic, so it goes to the
   * console and the caller's fallback is shown instead.
   */
  const refusalText = useCallback(
    async (res: Response, fallback: string): Promise<string> => {
      const { detail } = (await res.json().catch(() => ({}))) as ApiErrorPayload;
      console.error('Plugin import request refused:', res.status, detail);
      const key = resolveArchiveSecurityErrorI18nKey(resolveApiErrorDetail(detail, '').errorCode);
      return key ? tArchive(key as Parameters<typeof tArchive>[0]) : fallback;
    },
    [tArchive],
  );

  const reset = useCallback(() => {
    setParseError(null);
    setPreview(null);
    setDecisions({ skills: [], servers: [], agents: [] });
    setBindAgentId(null);
    setTrusted(false);
    setIsParsing(false);
    setIsImporting(false);
    setResult(null);
  }, []);

  const handleFilesSelected = useCallback(
    async (selectedFiles: FileList | File[]) => {
      const fileArray = Array.from(selectedFiles);
      if (fileArray.length !== 1) {
        setParseError(t('upload.singleArchiveOnly'));
        return;
      }
      const selected = fileArray[0];
      if (!selected.name.toLowerCase().endsWith('.zip')) {
        setParseError(t('upload.archiveOnly'));
        return;
      }
      if (selected.size > MAX_ARCHIVE_BYTES) {
        setParseError(t('upload.tooLarge'));
        return;
      }
      setParseError(null);
      setIsParsing(true);
      try {
        const formData = new FormData();
        formData.append('file', selected);
        const res = await fetch('/api/v1/plugins/import/preview', { method: 'POST', body: formData });
        if (!res.ok) {
          // 400: the file itself is unusable; anything else is the service failing.
          setParseError(
            await refusalText(res, t(res.status === 400 ? 'errors.previewFailed' : 'errors.requestFailed')),
          );
          return;
        }
        const data = (await res.json()) as PluginPreviewPayload;
        setPreview(data);
        setDecisions(defaultDecisions(data));
        if (agents.length === 0) {
          fetchAgents().catch(() => {});
        }
      } catch (error: unknown) {
        console.error('Plugin import preview failed:', error);
        setParseError(t('errors.requestFailed'));
      } finally {
        setIsParsing(false);
      }
    },
    [agents.length, fetchAgents, refusalText, t],
  );

  const setResolution = useCallback((kind: ComponentKind, virtualId: string, resolution: Resolution) => {
    setDecisions((prev) => ({
      ...prev,
      [kind]: prev[kind].map((item) => (item.virtual_id === virtualId ? { ...item, resolution } : item)),
    }));
  }, []);

  const setAll = useCallback(
    (kind: ComponentKind, target: 'install' | 'skip') => {
      if (!preview) {
        return;
      }
      setDecisions((prev) => ({
        ...prev,
        [kind]: prev[kind].map((item) => ({ ...item, resolution: bulkResolution(kind, preview, item, target) })),
      }));
    },
    [preview],
  );

  const confirm = useCallback(async () => {
    if (!preview) {
      return;
    }
    const toPayload = (component: 'skill' | 'mcp' | 'agent', items: ImportDecisions[ComponentKind]) =>
      items.map((item) => ({
        component,
        virtual_id: item.virtual_id,
        name: item.name,
        resolution: item.resolution,
      }));

    try {
      setIsImporting(true);
      const res = await fetch('/api/v1/plugins/import/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: preview.session_id,
          skills: toPayload('skill', decisions.skills),
          servers: toPayload('mcp', decisions.servers),
          agents: toPayload('agent', decisions.agents),
          bind_agent_id: bindAgentId,
        }),
      });
      if (!res.ok) {
        // 400: the staged upload is gone, so the file has to be uploaded again.
        const description = await refusalText(
          res,
          t(res.status === 400 ? 'errors.sessionExpired' : 'errors.confirmFailed'),
        );
        toast({ title: t('errors.confirmTitle'), description, variant: 'destructive' });
        return;
      }
      const data = (await res.json()) as PluginConfirmResult;
      setResult(data);
      onImportComplete();
      if (data.agents.length > 0) {
        fetchAgents(1, undefined, true).catch(() => {});
      }
    } catch (error: unknown) {
      console.error('Plugin import confirm failed:', error);
      toast({ title: t('errors.confirmTitle'), description: t('errors.confirmFailed'), variant: 'destructive' });
    } finally {
      setIsImporting(false);
    }
  }, [bindAgentId, decisions, fetchAgents, onImportComplete, preview, refusalText, t]);

  const close = useCallback(() => {
    reset();
    onOpenChange(false);
  }, [onOpenChange, reset]);

  const selected = useMemo(
    () => ({
      skills: countSelected(decisions.skills),
      servers: countSelected(decisions.servers),
      agents: countSelected(decisions.agents),
    }),
    [decisions],
  );

  return {
    agents,
    isParsing,
    isImporting,
    parseError,
    preview,
    decisions,
    bindAgentId,
    trusted,
    result,
    selected,
    handleFilesSelected,
    setResolution,
    setAll,
    setBindAgentId,
    setTrusted,
    confirm,
    reset,
    close,
  };
}
