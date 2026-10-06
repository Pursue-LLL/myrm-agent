'use client';

import { useCallback, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';

import { resolveUserFacingArchiveSecurityError } from '@/services/archiveSecurityErrorCore';
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

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim() ? error.message : fallback;
}

interface UsePluginImportFlowOptions {
  onOpenChange: (open: boolean) => void;
  onImportComplete: () => void;
}

/** Upload → preview → decide → confirm. The dialog only renders what this hook holds. */
export function usePluginImportFlow({ onOpenChange, onImportComplete }: UsePluginImportFlowOptions) {
  const t = useTranslations('settings.plugins.import');
  const { agents, fetchAgents } = useAgentStore();

  const [isParsing, setIsParsing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PluginPreviewPayload | null>(null);
  const [decisions, setDecisions] = useState<ImportDecisions>({ skills: [], servers: [], agents: [] });
  const [bindAgentId, setBindAgentId] = useState<string | null>(null);
  const [trusted, setTrusted] = useState(false);
  const [result, setResult] = useState<PluginConfirmResult | null>(null);

  const userFacingError = useCallback(
    (detail: unknown, fallback: string): string =>
      resolveUserFacingArchiveSecurityError(detail, fallback, (key) => t(key as Parameters<typeof t>[0])),
    [t],
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
          const errPayload = (await res.json().catch(() => ({}))) as ApiErrorPayload;
          throw new Error(userFacingError(errPayload.detail, t('errors.previewFailed')));
        }
        const data = (await res.json()) as PluginPreviewPayload;
        setPreview(data);
        setDecisions(defaultDecisions(data));
        if (agents.length === 0) {
          fetchAgents().catch(() => {});
        }
      } catch (error: unknown) {
        setParseError(errorMessage(error, t('errors.previewFailed')));
      } finally {
        setIsParsing(false);
      }
    },
    [agents.length, fetchAgents, t, userFacingError],
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
        const errPayload = (await res.json().catch(() => ({}))) as ApiErrorPayload;
        throw new Error(userFacingError(errPayload.detail, t('errors.confirmFailed')));
      }
      const data = (await res.json()) as PluginConfirmResult;
      setResult(data);
      onImportComplete();
      if (data.agents.length > 0) {
        fetchAgents(1, undefined, true).catch(() => {});
      }
    } catch (error: unknown) {
      toast({
        title: t('errors.confirmTitle'),
        description: errorMessage(error, t('errors.confirmFailed')),
        variant: 'destructive',
      });
    } finally {
      setIsImporting(false);
    }
  }, [bindAgentId, decisions, fetchAgents, onImportComplete, preview, t, userFacingError]);

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
