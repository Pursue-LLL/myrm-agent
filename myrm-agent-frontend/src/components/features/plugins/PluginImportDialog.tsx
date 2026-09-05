'use client';

import { memo, useCallback, useMemo, useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { useDragDrop } from '@/hooks/ui/useDragDrop';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import {
  IconUpload,
  IconPlug,
  IconCheck,
  IconX,
  IconAlertTriangle,
  IconLoader,
  IconShieldCheck,
  IconBot,
  IconTerminal,
  IconUsers,
  IconFolder,
} from '@/components/features/icons/PremiumIcons';
import { toast } from '@/hooks/shared/useToast';
import useAgentStore from '@/store/useAgentStore';
import { resolveUserFacingArchiveSecurityError } from '@/services/archiveSecurityErrorCore';
import { PluginTrustedSourceDisclosure } from './PluginTrustedSourceDisclosure';

interface PluginImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImportComplete: () => void;
}

interface CapabilityDiff {
  added: string[];
  removed: string[];
  has_escalation: boolean;
}

interface PluginMeta {
  name: string;
  version: string | null;
  description: string | null;
  author: Record<string, string> | null;
  homepage: string | null;
  repository: string | null;
  license: string | null;
  keywords: string[];
  capabilities?: string[];
  effective_tier?: string;
  risk_level?: string;
  capability_diff?: CapabilityDiff | null;
}

interface PluginSkillPreview {
  name: string;
  description: string;
  file_count: number;
  virtual_id: string;
  security_issues: string[];
  oversized_content: boolean;
  conflict: boolean;
}

interface PluginServerPreview {
  name: string;
  type: string;
  command: string | null;
  url: string | null;
  env_key_count: number;
  has_placeholders: boolean;
  virtual_id: string;
  missing_artifact?: string | null;
  is_runnable?: boolean;
  missing_artifacts?: string[];
  capabilities?: string[];
}

interface PluginAgentPreview {
  name: string;
  description: string;
  system_prompt: string;
  max_iterations: number | null;
  skill_names: string[];
  tool_names: string[];
  mcp_names: string[];
  subagent_names: string[];
  is_subagent: boolean;
  is_entry_agent: boolean;
  virtual_id: string;
}

interface PluginDiagnostic {
  component: string;
  code: string;
  message: string;
  level: string;
}

interface PluginPreviewPayload {
  session_id: string;
  plugin: PluginMeta;
  skills: PluginSkillPreview[];
  servers: PluginServerPreview[];
  agents?: PluginAgentPreview[];
  workspace_file_count?: number;
  diagnostics: PluginDiagnostic[];
  is_valid: boolean;
}

interface PluginConfirmResult {
  imported_skills: number;
  skipped_skills: number;
  imported_servers: number;
  skipped_servers: number;
  imported_agents?: number;
  skipped_agents?: number;
  created_agent_ids?: string[];
  required_secret_keys: string[];
}

interface ApiErrorPayload {
  detail?: unknown;
}

type ComponentDecision = {
  virtual_id: string;
  name: string;
  resolution: 'install' | 'replace' | 'skip';
};

function serverTypeLabel(type: string): 'local' | 'remote' {
  return type === 'stdio' ? 'local' : 'remote';
}

function isSkillBlocked(item: PluginSkillPreview): boolean {
  return item.security_issues.length > 0 || item.oversized_content;
}

function resolveErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

function getCapabilityTierBadgeStyle(tier: string): string {
  switch (tier) {
    case 'destructive':
      return 'border-destructive/40 text-destructive bg-destructive/10';
    case 'shell_exec':
      return 'border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-500/10';
    case 'network':
    case 'fs_write':
      return 'border-blue-500/40 text-blue-600 dark:text-blue-400 bg-blue-500/10';
    case 'fs_read':
      return 'border-muted-foreground/30 text-muted-foreground bg-muted/20';
    case 'read_only':
    default:
      return 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10';
  }
}

const PluginImportDialog = memo(({ open, onOpenChange, onImportComplete }: PluginImportDialogProps) => {
  const t = useTranslations('settings.plugins.import');
  const locale = useLocale();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { agents, fetchAgents } = useAgentStore();

  const resolveUserFacingApiError = useCallback(
    (detail: unknown, fallback: string): string =>
      resolveUserFacingArchiveSecurityError(detail, fallback, (key) => t(key as Parameters<typeof t>[0])),
    [t],
  );

  const [file, setFile] = useState<File | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PluginPreviewPayload | null>(null);
  const [skillDecisions, setSkillDecisions] = useState<ComponentDecision[]>([]);
  const [serverDecisions, setServerDecisions] = useState<ComponentDecision[]>([]);
  const [agentDecisions, setAgentDecisions] = useState<ComponentDecision[]>([]);
  const [bindAgentId, setBindAgentId] = useState<string | null>(null);
  const [trusted, setTrusted] = useState(false);

  const resetForm = useCallback(() => {
    setFile(null);
    setParseError(null);
    setPreview(null);
    setSkillDecisions([]);
    setServerDecisions([]);
    setAgentDecisions([]);
    setBindAgentId(null);
    setTrusted(false);
    setIsParsing(false);
    setIsImporting(false);
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
      if (selected.size > 20 * 1024 * 1024) {
        setParseError(t('upload.tooLarge'));
        return;
      }
      setParseError(null);
      setFile(selected);
      setIsParsing(true);
      try {
        const formData = new FormData();
        formData.append('file', selected);

        const res = await fetch('/api/v1/plugins/import/preview', {
          method: 'POST',
          body: formData,
        });

        if (!res.ok) {
          const errPayload = (await res.json().catch(() => ({}))) as ApiErrorPayload;
          throw new Error(resolveUserFacingApiError(errPayload.detail, t('errors.previewFailed')));
        }

        const data = (await res.json()) as PluginPreviewPayload;
        setPreview(data);
        setSkillDecisions(
          data.skills.map((item) => ({
            virtual_id: item.virtual_id,
            name: item.name,
            resolution: isSkillBlocked(item) || item.conflict ? 'skip' : 'install',
          })),
        );
        setServerDecisions(
          data.servers.map((item) => ({
            virtual_id: item.virtual_id,
            name: item.name,
            resolution: item.missing_artifact || item.is_runnable === false ? 'skip' : 'install',
          })),
        );
        setAgentDecisions(
          (data.agents ?? []).map((item) => ({
            virtual_id: item.virtual_id,
            name: item.name,
            resolution: 'install',
          })),
        );
        if (agents.length === 0) {
          fetchAgents().catch(() => {});
        }
      } catch (error: unknown) {
        setParseError(resolveErrorMessage(error, t('errors.previewFailed')));
        setFile(null);
      } finally {
        setIsParsing(false);
      }
    },
    [resolveUserFacingApiError, t, agents.length, fetchAgents],
  );

  const { isDragging, dragHandlers } = useDragDrop({
    onFilesSelected: handleFilesSelected,
    accept: ['application/zip'],
    maxFiles: 1,
    disabled: isParsing || isImporting,
  });

  const setResolution = useCallback(
    (list: ComponentDecision[], setList: (v: ComponentDecision[]) => void) =>
      (virtualId: string, resolution: ComponentDecision['resolution']) => {
        setList(list.map((item) => (item.virtual_id === virtualId ? { ...item, resolution } : item)));
      },
    [],
  );

  const toggleAllSkills = useCallback(
    (resolution: 'install' | 'skip') => {
      setSkillDecisions((prev) =>
        prev.map((item) => {
          const skill = preview?.skills.find((s) => s.virtual_id === item.virtual_id);
          const isBlocked = skill ? isSkillBlocked(skill) : false;
          if (isBlocked && resolution === 'install') {
            return item;
          }
          if (skill?.conflict) {
            // A conflicting skill is upgraded in place, not duplicated.
            return { ...item, resolution: resolution === 'install' ? 'replace' : 'skip' };
          }
          return { ...item, resolution };
        }),
      );
    },
    [preview],
  );

  const toggleAllServers = useCallback(
    (resolution: 'install' | 'skip') => {
      setServerDecisions((prev) =>
        prev.map((item) => {
          const server = preview?.servers.find((s) => s.virtual_id === item.virtual_id);
          if ((server?.missing_artifact || server?.is_runnable === false) && resolution === 'install') {
            return { ...item, resolution: 'skip' };
          }
          return { ...item, resolution };
        }),
      );
    },
    [preview],
  );

  const toggleAllAgents = useCallback((resolution: 'install' | 'skip') => {
    setAgentDecisions((prev) => prev.map((item) => ({ ...item, resolution })));
  }, []);

  const handleConfirmImport = useCallback(async () => {
    if (!preview) {
      return;
    }
    try {
      setIsImporting(true);
      const payload = {
        session_id: preview.session_id,
        skills: skillDecisions.map((item) => ({
          component: 'skill',
          virtual_id: item.virtual_id,
          name: item.name,
          resolution: item.resolution,
        })),
        servers: serverDecisions.map((item) => ({
          component: 'mcp',
          virtual_id: item.virtual_id,
          name: item.name,
          resolution: item.resolution,
        })),
        agents: agentDecisions.map((item) => ({
          component: 'agent',
          virtual_id: item.virtual_id,
          name: item.name,
          resolution: item.resolution,
        })),
        bind_agent_id: bindAgentId,
      };

      const res = await fetch('/api/v1/plugins/import/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errPayload = (await res.json().catch(() => ({}))) as ApiErrorPayload;
        throw new Error(resolveUserFacingApiError(errPayload.detail, t('errors.confirmFailed')));
      }

      const result = (await res.json()) as PluginConfirmResult;
      const secretKeys = result.required_secret_keys ?? [];
      const importedAgents = result.imported_agents ?? 0;
      toast({
        title: t('success.title'),
        description: [
          t('success.description', {
            agents: importedAgents,
            skills: result.imported_skills,
            servers: result.imported_servers,
          }),
          secretKeys.length > 0 ? t('success.requiredKeys', { keys: secretKeys.join(', ') }) : '',
          result.imported_servers > 0 ? t('success.disabledHint') : '',
        ]
          .filter(Boolean)
          .join('\n'),
      });
      resetForm();
      onOpenChange(false);
      onImportComplete();
    } catch (error: unknown) {
      toast({
        title: t('errors.confirmTitle'),
        description: resolveErrorMessage(error, t('errors.confirmFailed')),
        variant: 'destructive',
      });
    } finally {
      setIsImporting(false);
    }
  }, [
    preview,
    skillDecisions,
    serverDecisions,
    agentDecisions,
    bindAgentId,
    resolveUserFacingApiError,
    t,
    resetForm,
    onOpenChange,
    onImportComplete,
  ]);

  const installedSkillCount = useMemo(
    () => skillDecisions.filter((item) => item.resolution === 'install' || item.resolution === 'replace').length,
    [skillDecisions],
  );
  const installedServerCount = useMemo(
    () => serverDecisions.filter((item) => item.resolution === 'install').length,
    [serverDecisions],
  );
  const installedAgentCount = useMemo(
    () => agentDecisions.filter((item) => item.resolution === 'install').length,
    [agentDecisions],
  );

  return (
    <Dialog
      open={open}
      onOpenChange={(val) => {
        if (!val) {
          resetForm();
        }
        onOpenChange(val);
      }}
    >
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col p-0 overflow-hidden">
        <DialogHeader className="p-6 pb-4 border-b">
          <DialogTitle className="flex items-center gap-2 text-xl">
            <IconPlug className="w-5 h-5" />
            {t('title')}
          </DialogTitle>
          <DialogDescription>{t('subtitle')}</DialogDescription>
        </DialogHeader>

        <ScrollArea className="flex-1 px-6 bg-muted/10">
          <div className="py-6 space-y-6">
            {!file ? (
              <label
                className={cn(
                  'block cursor-pointer rounded-xl border-2 border-dashed p-12 text-center transition-colors bg-background',
                  isDragging && 'border-primary bg-primary/5',
                  parseError && 'border-destructive bg-destructive/5',
                  !isDragging && !parseError && 'border-muted-foreground/25 hover:border-primary/50',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                )}
                {...dragHandlers}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip"
                  className="sr-only"
                  onChange={(e) => {
                    if (e.target.files?.length) {
                      handleFilesSelected(e.target.files);
                    }
                  }}
                />
                {isParsing ? (
                  <IconLoader className="w-10 h-10 mx-auto mb-4 animate-spin text-primary" />
                ) : (
                  <IconUpload
                    className={cn('w-10 h-10 mx-auto mb-4', parseError ? 'text-destructive' : 'text-muted-foreground')}
                  />
                )}

                <p className="text-base font-medium">{isParsing ? t('upload.parsing') : t('upload.dropHint')}</p>
                <p className="text-sm text-muted-foreground mt-2">{t('upload.keyboardHint')}</p>
                <p className="text-sm text-muted-foreground mt-1">{t('upload.formatHint')}</p>

                {parseError && (
                  <Alert variant="destructive" className="mt-6 text-left inline-block">
                    <IconAlertTriangle className="h-4 w-4" />
                    <AlertTitle>{t('errors.parseTitle')}</AlertTitle>
                    <AlertDescription>{parseError}</AlertDescription>
                  </Alert>
                )}
              </label>
            ) : preview ? (
              <div className="space-y-6">
                {/* Plugin card */}
                <div className="p-4 rounded-xl border bg-background flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                      <IconPlug className="w-5 h-5 text-primary" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-medium text-base">{preview.plugin.name}</h3>
                        {preview.plugin.version && (
                          <Badge variant="outline" className="text-xs">
                            v{preview.plugin.version}
                          </Badge>
                        )}
                        {preview.plugin.license && (
                          <Badge variant="secondary" className="text-xs">
                            {preview.plugin.license}
                          </Badge>
                        )}
                        {preview.plugin.risk_level && (
                          <Badge
                            variant={preview.plugin.risk_level === 'critical' ? 'destructive' : 'outline'}
                            className={cn(
                              'text-xs font-normal',
                              preview.plugin.risk_level === 'high' &&
                                'border-amber-500/50 text-amber-600 dark:text-amber-400 bg-amber-500/10',
                              preview.plugin.risk_level === 'medium' &&
                                'border-blue-500/50 text-blue-600 dark:text-blue-400 bg-blue-500/10',
                              preview.plugin.risk_level === 'low' &&
                                'border-emerald-500/50 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10',
                            )}
                          >
                            <IconShieldCheck className="w-3 h-3 mr-1 inline-block" />
                            {t(`capabilities.risk.${preview.plugin.risk_level}` as Parameters<typeof t>[0])}
                          </Badge>
                        )}
                      </div>
                      {preview.plugin.description && (
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{preview.plugin.description}</p>
                      )}
                      {preview.plugin.capabilities && preview.plugin.capabilities.length > 0 && (
                        <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                          <span className="text-[11px] text-muted-foreground font-medium mr-0.5">
                            {t('capabilities.title')}:
                          </span>
                          {preview.plugin.capabilities.map((cap) => (
                            <Badge
                              key={cap}
                              variant="outline"
                              className={cn('text-[10px] px-1.5 py-0 font-normal', getCapabilityTierBadgeStyle(cap))}
                            >
                              {t(`capabilities.${cap}` as Parameters<typeof t>[0])}
                            </Badge>
                          ))}
                        </div>
                      )}
                      <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                        {preview.plugin.author?.name && (
                          <span className="flex items-center gap-1">
                            <IconBot className="w-3 h-3" />
                            {preview.plugin.author.name}
                          </span>
                        )}
                        {(preview.plugin.keywords ?? []).slice(0, 5).map((kw) => (
                          <Badge key={kw} variant="outline" className="text-[10px] px-1.5 py-0">
                            {kw}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  </div>
                  <Button variant="ghost" size="sm" onClick={resetForm} disabled={isImporting}>
                    {t('actions.reselect')}
                  </Button>
                </div>

                {/* Capability Escalation Warning */}
                {preview.plugin.capability_diff?.has_escalation && (
                  <Alert variant="destructive" className="py-2.5">
                    <IconAlertTriangle className="h-4 w-4" />
                    <AlertTitle className="text-xs font-semibold">{t('capabilities.escalationTitle')}</AlertTitle>
                    <AlertDescription className="text-xs mt-0.5">
                      {t('capabilities.escalationWarning', {
                        added: preview.plugin.capability_diff.added
                          .map((c) => t(`capabilities.${c}` as Parameters<typeof t>[0]))
                          .join(', '),
                      })}
                    </AlertDescription>
                  </Alert>
                )}

                {/* Diagnostics */}
                {preview.diagnostics.length > 0 && (
                  <div className="space-y-2">
                    {preview.diagnostics.map((diag, idx) => (
                      <Alert key={idx} variant={diag.level === 'error' ? 'destructive' : 'default'} className="py-2">
                        <IconAlertTriangle className="h-4 w-4" />
                        <AlertTitle className="text-xs font-medium">{diag.component}</AlertTitle>
                        <AlertDescription className="text-xs">{diag.message}</AlertDescription>
                      </Alert>
                    ))}
                  </div>
                )}

                {/* Empty state: no importable components */}
                {preview.skills.length === 0 &&
                  preview.servers.length === 0 &&
                  (!preview.agents || preview.agents.length === 0) && (
                    <div className="rounded-xl border border-dashed p-6 text-center">
                      <p className="text-sm font-medium">{t('empty.title')}</p>
                      <p className="text-sm text-muted-foreground mt-1">{t('empty.hint')}</p>
                    </div>
                  )}

                {/* Agents / Squad */}
                {preview.agents && preview.agents.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="font-medium text-base flex items-center gap-2">
                        <IconUsers className="w-4 h-4 text-primary" />
                        {t('sections.agents', { count: preview.agents.length })}
                      </h4>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => toggleAllAgents('install')}
                        >
                          {t('actions.selectAll')}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => toggleAllAgents('skip')}
                        >
                          {t('actions.skipAll')}
                        </Button>
                      </div>
                    </div>
                    <div className="rounded-xl border bg-background divide-y">
                      {preview.agents.map((item) => {
                        const decision = agentDecisions.find((d) => d.virtual_id === item.virtual_id);
                        const isInstalled = decision?.resolution === 'install';
                        return (
                          <div key={item.virtual_id} className="flex items-center justify-between gap-3 px-4 py-3">
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2 flex-wrap">
                                <p className="text-sm font-medium">{item.name}</p>
                                {item.is_entry_agent && (
                                  <Badge variant="default" className="text-[10px] py-0 px-1.5 font-normal">
                                    {t('agents.entry')}
                                  </Badge>
                                )}
                                {item.is_subagent && !item.is_entry_agent && (
                                  <Badge variant="secondary" className="text-[10px] py-0 px-1.5 font-normal">
                                    {t('agents.subagent')}
                                  </Badge>
                                )}
                              </div>
                              {item.description && (
                                <p className="text-xs text-muted-foreground truncate mt-0.5">{item.description}</p>
                              )}
                              <div className="flex items-center gap-2 mt-1 text-[11px] text-muted-foreground flex-wrap">
                                {item.skill_names.length > 0 && (
                                  <span>{t('agents.skillsCount', { count: item.skill_names.length })}</span>
                                )}
                                {item.tool_names.length > 0 && (
                                  <span>· {t('agents.toolsCount', { count: item.tool_names.length })}</span>
                                )}
                                {item.subagent_names.length > 0 && (
                                  <span>· {t('agents.subagentsCount', { count: item.subagent_names.length })}</span>
                                )}
                              </div>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <Button
                                variant={isInstalled ? 'default' : 'ghost'}
                                size="sm"
                                className="h-7 px-2 text-xs"
                                disabled={isImporting}
                                onClick={() =>
                                  setResolution(agentDecisions, setAgentDecisions)(
                                    item.virtual_id,
                                    isInstalled ? 'skip' : 'install',
                                  )
                                }
                              >
                                {isInstalled ? (
                                  <IconCheck className="w-3 h-3 mr-1" />
                                ) : (
                                  <IconX className="w-3 h-3 mr-1" />
                                )}
                                {isInstalled ? t('actions.install') : t('actions.skip')}
                              </Button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Workspace Template Assets Notice */}
                {(preview.workspace_file_count ?? 0) > 0 && (
                  <div className="rounded-xl border bg-muted/20 px-4 py-3 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm">
                      <IconFolder className="w-4 h-4 text-primary" />
                      <span className="font-medium">
                        {t('sections.workspaceFiles', { count: preview.workspace_file_count })}
                      </span>
                    </div>
                    <Badge variant="outline" className="text-xs">
                      {t('agents.templateFiles', { count: preview.workspace_file_count })}
                    </Badge>
                  </div>
                )}

                {/* Skills */}
                {preview.skills.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="font-medium text-base flex items-center gap-2">
                        <IconShieldCheck className="w-4 h-4 text-primary" />
                        {t('sections.skills', { count: preview.skills.length })}
                      </h4>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => toggleAllSkills('install')}
                        >
                          {t('actions.selectAll')}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => toggleAllSkills('skip')}
                        >
                          {t('actions.skipAll')}
                        </Button>
                      </div>
                    </div>
                    <div className="rounded-xl border bg-background divide-y">
                      {preview.skills.map((item) => {
                        const decision = skillDecisions.find((d) => d.virtual_id === item.virtual_id);
                        const isInstalled = decision?.resolution === 'install';
                        const isReplacing = decision?.resolution === 'replace';
                        const isBlocked = isSkillBlocked(item);
                        return (
                          <div key={item.virtual_id} className="flex items-center justify-between gap-3 px-4 py-3">
                            <div className="min-w-0">
                              <p className="text-sm font-medium">{item.name}</p>
                              {item.description && !isBlocked && (
                                <p className="text-xs text-muted-foreground truncate">{item.description}</p>
                              )}
                              {item.oversized_content && (
                                <p className="text-xs text-destructive mt-0.5">{t('security.oversized')}</p>
                              )}
                              {isBlocked && !item.oversized_content && (
                                <p className="text-xs text-destructive mt-0.5">
                                  {t('security.blocked', { count: item.security_issues.length })}
                                </p>
                              )}
                              {item.conflict && !isBlocked && (
                                <p className="text-xs text-amber-600 dark:text-amber-400 mt-0.5">
                                  {t('security.conflict')}
                                </p>
                              )}
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              {!isBlocked && (
                                <>
                                  <Badge variant="outline" className="text-[10px]">
                                    {item.file_count} {t('sections.files')}
                                  </Badge>
                                  <Button
                                    variant={isInstalled || isReplacing ? 'default' : 'ghost'}
                                    size="sm"
                                    className="h-7 px-2 text-xs"
                                    disabled={isImporting}
                                    onClick={() =>
                                      setResolution(skillDecisions, setSkillDecisions)(
                                        item.virtual_id,
                                        item.conflict
                                          ? isReplacing
                                            ? 'skip'
                                            : 'replace'
                                          : isInstalled
                                            ? 'skip'
                                            : 'install',
                                      )
                                    }
                                  >
                                    {isInstalled || isReplacing ? (
                                      <IconCheck className="w-3 h-3 mr-1" />
                                    ) : (
                                      <IconX className="w-3 h-3 mr-1" />
                                    )}
                                    {item.conflict
                                      ? isReplacing
                                        ? t('actions.replace')
                                        : t('actions.skip')
                                      : isInstalled
                                        ? t('actions.install')
                                        : t('actions.skip')}
                                  </Button>
                                </>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* MCP servers */}
                {preview.servers.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="font-medium text-base flex items-center gap-2">
                        <IconTerminal className="w-4 h-4 text-primary" />
                        {t('sections.servers', { count: preview.servers.length })}
                      </h4>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => toggleAllServers('install')}
                        >
                          {t('actions.selectAll')}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => toggleAllServers('skip')}
                        >
                          {t('actions.skipAll')}
                        </Button>
                      </div>
                    </div>
                    <div className="rounded-xl border bg-background divide-y">
                      {preview.servers.map((item) => {
                        const decision = serverDecisions.find((d) => d.virtual_id === item.virtual_id);
                        const isInstalled = decision?.resolution === 'install';
                        const isMissingArtifact = Boolean(item.missing_artifact) || item.is_runnable === false;
                        const missingFile = item.missing_artifact || item.missing_artifacts?.[0] || '';
                        const undeclaredDiag = preview.diagnostics.find(
                          (d) => d.code === 'capability_undeclared_privilege' && d.component === `mcp:${item.name}`,
                        );
                        return (
                          <div key={item.virtual_id} className="flex items-center justify-between gap-3 px-4 py-3">
                            <div className="min-w-0">
                              <p className="text-sm font-medium">{item.name}</p>
                              <p className="text-xs text-muted-foreground truncate">
                                {t(`serverType.${serverTypeLabel(item.type)}`)}
                                {item.command ? ` · ${item.command}` : ''}
                                {item.url ? ` · ${item.url}` : ''}
                                {item.has_placeholders ? ` · ${t('sections.placeholder')}` : ''}
                              </p>
                              {item.capabilities && item.capabilities.length > 0 && (
                                <div className="flex items-center gap-1 mt-1 flex-wrap">
                                  {item.capabilities.map((cap) => (
                                    <Badge
                                      key={cap}
                                      variant="outline"
                                      className={cn(
                                        'text-[10px] px-1 py-0 font-normal',
                                        getCapabilityTierBadgeStyle(cap),
                                      )}
                                    >
                                      {t(`capabilities.${cap}` as Parameters<typeof t>[0])}
                                    </Badge>
                                  ))}
                                </div>
                              )}
                              {isMissingArtifact && (
                                <p className="text-xs text-destructive mt-0.5">
                                  {t('security.missingArtifact', { file: missingFile })}
                                </p>
                              )}
                              {undeclaredDiag && (
                                <p className="text-xs text-amber-600 dark:text-amber-400 mt-1 flex items-center gap-1 font-medium">
                                  <IconAlertTriangle className="w-3.5 h-3.5 inline shrink-0" />
                                  {t('capabilities.undeclaredWarning')}
                                </p>
                              )}
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              {item.env_key_count > 0 && (
                                <Badge variant="outline" className="text-[10px]">
                                  {t('sections.envCount', { count: item.env_key_count })}
                                </Badge>
                              )}
                              <Button
                                variant={isInstalled ? 'default' : 'ghost'}
                                size="sm"
                                className="h-7 px-2 text-xs"
                                disabled={isImporting || isMissingArtifact}
                                onClick={() =>
                                  setResolution(serverDecisions, setServerDecisions)(
                                    item.virtual_id,
                                    isInstalled ? 'skip' : 'install',
                                  )
                                }
                              >
                                {isInstalled ? (
                                  <IconCheck className="w-3 h-3 mr-1" />
                                ) : (
                                  <IconX className="w-3 h-3 mr-1" />
                                )}
                                {isInstalled ? t('actions.install') : t('actions.skip')}
                              </Button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Bind agent */}
                {(preview.skills.length > 0 || preview.servers.length > 0) && (
                  <div className="space-y-2">
                    <label className="text-sm font-medium flex items-center gap-2">
                      <IconBot className="w-4 h-4 text-muted-foreground" />
                      {t('bind.label')}
                    </label>
                    <Select value={bindAgentId ?? undefined} onValueChange={setBindAgentId} disabled={isImporting}>
                      <SelectTrigger className="w-full sm:w-[280px]">
                        <SelectValue placeholder={t('bind.placeholder')} />
                      </SelectTrigger>
                      <SelectContent>
                        {agents.map((agent) => (
                          <SelectItem key={agent.id} value={agent.id}>
                            {getBuiltinAgentName(agent.id, agent.name || agent.id, locale)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">{t('bind.hint')}</p>
                  </div>
                )}

                {/* Trusted Source & Sandbox Security Disclosure */}
                <PluginTrustedSourceDisclosure trusted={trusted} onTrustChange={setTrusted} disabled={isImporting} />
              </div>
            ) : null}
          </div>
        </ScrollArea>

        {preview && (
          <div className="p-4 border-t flex items-center justify-between gap-3">
            <div className="text-xs text-muted-foreground">
              {t('summary', {
                agents: installedAgentCount,
                skills: installedSkillCount,
                servers: installedServerCount,
              })}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={resetForm} disabled={isImporting}>
                {t('actions.cancel')}
              </Button>
              <Button
                size="sm"
                onClick={handleConfirmImport}
                disabled={
                  isImporting || (!installedSkillCount && !installedServerCount && !installedAgentCount) || !trusted
                }
              >
                {isImporting && <IconLoader className="w-4 h-4 mr-2 animate-spin" />}
                {t('actions.confirm')}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
});

PluginImportDialog.displayName = 'PluginImportDialog';

export default PluginImportDialog;
