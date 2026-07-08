'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import {
  IconBot,
  IconCode,
  IconLoader,
  IconPencil,
  IconPlug,
  IconPlus,
  IconTerminal,
  IconTrash,
  IconZap,
} from '@/components/features/icons/PremiumIcons';
import { useTranslations } from 'next-intl';
import { Skeleton } from '@/components/primitives/skeleton';
import { toast } from 'sonner';

import { Switch } from '@/components/primitives/switch';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import { Button } from '@/components/primitives/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { apiRequest } from '@/lib/api';
import { isLocalMode } from '@/lib/deploy-mode';
import {
  getConfigSyncManager,
  type ExternalAgentConfig,
  type ExternalAgentType,
  type ExternalAgentPermissionMode,
  type ExternalAgentAuthMode,
  type ExternalAgentsConfigValue,
} from '@/services/config';
import { getExternalAgentAuthStatus, type ExternalAgentAuthStatus } from '@/services/external-agents';
import ExternalAgentAuthControls from './ExternalAgentAuthControls';
import SettingsSection from '../SettingsSection';

const DEFAULT_AGENT: ExternalAgentConfig = {
  name: '',
  type: 'cli',
  command: '',
  args: [],
  enabled: true,
  permissionMode: 'safe',
  authMode: 'subscription',
  description: '',
  maxTurns: 25,
};

/** Map a CLI command to its known auth backend key (codex/claude/gemini/qwen). */
const KNOWN_BACKENDS = ['codex', 'claude', 'gemini', 'qwen'] as const;
function backendKeyFromCommand(command: string): string | null {
  const base = (command.split(/[\\/]/).pop() ?? '').toLowerCase().split('.')[0];
  if (KNOWN_BACKENDS.includes(base as (typeof KNOWN_BACKENDS)[number])) return base;
  return KNOWN_BACKENDS.find((b) => base.includes(b)) ?? null;
}

const AGENT_PRESETS: { key: string; config: ExternalAgentConfig }[] = [
  {
    key: 'claude',
    config: {
      ...DEFAULT_AGENT,
      name: 'claude-code',
      command: 'claude',
      args: ['--output-format', 'stream-json', '-p'],
      description: 'Full-stack coding agent powered by Anthropic Claude',
    },
  },
  {
    key: 'codex',
    config: {
      ...DEFAULT_AGENT,
      name: 'codex-cli',
      command: 'codex',
      args: ['exec', '--json', '--full-auto'],
      description: 'OpenAI Codex CLI coding agent (requires Responses API provider)',
    },
  },
  {
    key: 'gemini',
    config: {
      ...DEFAULT_AGENT,
      name: 'gemini-cli',
      command: 'gemini',
      args: ['--output-format', 'stream-json', '--yolo'],
      description: 'Google Gemini-powered coding agent',
    },
  },
];

const TYPE_ICONS: Record<ExternalAgentType, React.ElementType> = {
  cli: IconTerminal,
  acp: IconPlug,
  sdk: IconCode,
};

const syncManager = getConfigSyncManager();

const ExternalAgentsConfig = memo(() => {
  const t = useTranslations('settings.developer.externalAgents');
  const [agents, setAgents] = useState<ExternalAgentConfig[]>([]);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [draft, setDraft] = useState<ExternalAgentConfig>(DEFAULT_AGENT);
  const [deleteIndex, setDeleteIndex] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isTesting, setIsTesting] = useState(false);
  const [authStatuses, setAuthStatuses] = useState<ExternalAgentAuthStatus[]>([]);

  const refreshAuthStatuses = useCallback(async () => {
    try {
      setAuthStatuses(await getExternalAgentAuthStatus());
    } catch {
      // Login state is advisory; never block the settings UI on it.
    }
  }, []);

  const statusForCommand = useCallback(
    (command: string): ExternalAgentAuthStatus | null => {
      const key = backendKeyFromCommand(command);
      if (!key) return null;
      return authStatuses.find((s) => s.backend === key) ?? null;
    },
    [authStatuses],
  );

  useEffect(() => {
    (async () => {
      try {
        const config = syncManager.get('externalAgents');
        if (config?.agents) {
          setAgents(config.agents);
        }
      } catch {
        // No config yet
      } finally {
        setIsLoading(false);
      }
    })();
    void refreshAuthStatuses();
  }, [refreshAuthStatuses]);

  const persist = useCallback((updated: ExternalAgentConfig[]) => {
    setAgents(updated);
    const value: ExternalAgentsConfigValue = { agents: updated };
    syncManager.set('externalAgents', value);
  }, []);

  const handleToggle = useCallback(
    (index: number) => {
      const updated = agents.map((a, i) => (i === index ? { ...a, enabled: !a.enabled } : a));
      persist(updated);
    },
    [agents, persist],
  );

  const handleStartAdd = useCallback(() => {
    setDraft({ ...DEFAULT_AGENT });
    setEditingIndex(-1);
  }, []);

  const handleStartEdit = useCallback(
    (index: number) => {
      setDraft({ ...agents[index] });
      setEditingIndex(index);
    },
    [agents],
  );

  const handleSave = useCallback(() => {
    const trimmedName = draft.name.trim();
    if (!trimmedName) {
      toast.error(t('nameRequired'));
      return;
    }
    if (!draft.command.trim()) {
      toast.error(t('commandRequired'));
      return;
    }

    const duplicate = agents.some((a, i) => a.name === trimmedName && i !== editingIndex);
    if (duplicate) {
      toast.error(t('nameDuplicate'));
      return;
    }

    const cleaned: ExternalAgentConfig = {
      ...draft,
      name: trimmedName,
      command: draft.command.trim(),
      args: (draft.args ?? []).filter((a) => a.trim() !== ''),
    };

    let updated: ExternalAgentConfig[];
    if (editingIndex === -1) {
      updated = [...agents, cleaned];
    } else {
      updated = agents.map((a, i) => (i === editingIndex ? cleaned : a));
    }
    persist(updated);
    setEditingIndex(null);
  }, [draft, editingIndex, agents, persist, t]);

  const handleDelete = useCallback(() => {
    if (deleteIndex === null) return;
    const updated = agents.filter((_, i) => i !== deleteIndex);
    persist(updated);
    setDeleteIndex(null);
    if (editingIndex === deleteIndex) setEditingIndex(null);
  }, [deleteIndex, agents, persist, editingIndex]);

  const handleCancel = useCallback(() => {
    setEditingIndex(null);
  }, []);

  const handleTest = useCallback(async () => {
    const command = draft.command.trim();
    if (!command) {
      toast.error(t('commandRequired'));
      return;
    }
    setIsTesting(true);
    try {
      const result = await apiRequest<{ ok: boolean; message: string }>('/channels/manage/external-agents/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command }),
      });
      if (result.ok) {
        toast.success(result.message);
      } else {
        toast.error(result.message);
      }
    } catch {
      toast.error(t('testFailed'));
    } finally {
      setIsTesting(false);
    }
  }, [draft.command, t]);

  if (isLoading) {
    return (
      <SettingsSection title={t('title')} description={t('description')}>
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 p-3 rounded-lg border border-border/40">
              <Skeleton className="h-9 w-9 rounded-lg" />
              <div className="flex-1 space-y-1.5">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-3 w-48" />
              </div>
            </div>
          ))}
        </div>
      </SettingsSection>
    );
  }

  const isEditing = editingIndex !== null;

  return (
    <>
      <SettingsSection
        title={t('title')}
        description={t('description')}
        action={
          !isEditing ? (
            <Button onClick={handleStartAdd} size="sm">
              <IconPlus className="w-4 h-4 mr-1.5" />
              {t('add')}
            </Button>
          ) : undefined
        }
      >
        {isLocalMode() && <p className="text-xs text-muted-foreground -mt-2">{t('tauriAutoDetect')}</p>}
        <p className="text-xs text-muted-foreground">{t('agentToggleHint')}</p>

        {agents.length === 0 && !isEditing && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <IconBot className="w-10 h-10 text-muted-foreground/40 mb-3" />
            <p className="text-sm text-muted-foreground">{t('empty')}</p>
            <p className="text-xs text-muted-foreground/60 mt-1">{t('emptyHint')}</p>
          </div>
        )}

        {agents.length > 0 && (
          <div className="space-y-2">
            {agents.map((agent, index) => {
              const TypeIcon = TYPE_ICONS[agent.type] ?? IconTerminal;
              return (
                <div
                  key={`${agent.name}-${index}`}
                  className="flex items-center justify-between p-3 rounded-lg border border-border bg-background/50 hover:bg-muted/40 transition-colors group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div onClick={(e) => e.stopPropagation()}>
                      <Switch checked={agent.enabled} onCheckedChange={() => handleToggle(index)} />
                    </div>
                    <TypeIcon className="w-4 h-4 text-muted-foreground shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{agent.name}</p>
                      <p className="text-xs text-muted-foreground truncate">
                        {agent.command} {(agent.args ?? []).join(' ')}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <ExternalAgentAuthControls
                      command={agent.command}
                      status={statusForCommand(agent.command)}
                      onChanged={refreshAuthStatuses}
                    />
                    <button
                      onClick={() => handleStartEdit(index)}
                      className="p-1.5 opacity-0 group-hover:opacity-100 hover:bg-muted rounded transition-all"
                    >
                      <IconPencil className="w-3.5 h-3.5 text-muted-foreground" />
                    </button>
                    <button
                      onClick={() => setDeleteIndex(index)}
                      className="p-1.5 opacity-0 group-hover:opacity-100 hover:bg-muted rounded transition-all"
                    >
                      <IconTrash className="w-3.5 h-3.5 text-red-500" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {isEditing && (
          <div className="border border-border rounded-lg p-4 space-y-4 bg-muted/20">
            {editingIndex === -1 && (
              <div className="flex flex-wrap gap-2">
                <span className="text-xs text-muted-foreground self-center mr-1">{t('presets')}:</span>
                {AGENT_PRESETS.map((preset) => (
                  <button
                    key={preset.key}
                    onClick={() => setDraft({ ...preset.config })}
                    className="text-xs px-2.5 py-1 rounded-full border border-border hover:bg-muted transition-colors"
                  >
                    {t(`preset_${preset.key}` as Parameters<typeof t>[0])}
                  </button>
                ))}
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{t('name')}</label>
                <Input
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  placeholder={t('namePlaceholder')}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{t('type')}</label>
                <Select value={draft.type} onValueChange={(v: ExternalAgentType) => setDraft({ ...draft, type: v })}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cli">{t('typeCli')}</SelectItem>
                    <SelectItem value="acp">{t('typeAcp')}</SelectItem>
                    <SelectItem value="sdk">{t('typeSdk')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">{t('command')}</label>
              <Input
                value={draft.command}
                onChange={(e) => setDraft({ ...draft, command: e.target.value })}
                placeholder={t('commandPlaceholder')}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">{t('args')}</label>
              <Textarea
                value={(draft.args ?? []).join('\n')}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    args: e.target.value ? e.target.value.split('\n') : [],
                  })
                }
                placeholder={t('argsPlaceholder')}
                rows={2}
                className="resize-none"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">{t('descriptionLabel')}</label>
              <Textarea
                value={draft.description ?? ''}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                placeholder={t('descriptionPlaceholder')}
                rows={2}
                className="resize-none"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{t('permissionMode')}</label>
                <Select
                  value={draft.permissionMode}
                  onValueChange={(v: ExternalAgentPermissionMode) => setDraft({ ...draft, permissionMode: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="allow_all">{t('permissionAllowAll')}</SelectItem>
                    <SelectItem value="ask">{t('permissionAsk')}</SelectItem>
                    <SelectItem value="safe">{t('permissionSafe')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{t('maxTurns')}</label>
                <Input
                  type="number"
                  min={1}
                  max={200}
                  value={draft.maxTurns ?? 25}
                  onChange={(e) => setDraft({ ...draft, maxTurns: parseInt(e.target.value, 10) || 25 })}
                />
                <p className="text-[11px] text-muted-foreground/60">{t('maxTurnsHint')}</p>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">{t('authMode')}</label>
              <Select
                value={draft.authMode ?? 'subscription'}
                onValueChange={(v: ExternalAgentAuthMode) => setDraft({ ...draft, authMode: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="subscription">{t('authModeSubscription')}</SelectItem>
                  <SelectItem value="api_key">{t('authModeApiKey')}</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground/60">{t('authModeHint')}</p>
            </div>

            <div className="flex items-center gap-2">
              <Switch checked={draft.enabled} onCheckedChange={(checked) => setDraft({ ...draft, enabled: checked })} />
              <span className="text-sm">{t('enabled')}</span>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              {isLocalMode() && (
                <Button variant="ghost" size="sm" onClick={handleTest} disabled={isTesting || !draft.command.trim()}>
                  {isTesting ? (
                    <IconLoader className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                  ) : (
                    <IconZap className="w-3.5 h-3.5 mr-1.5" />
                  )}
                  {t('testConnection')}
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={handleCancel}>
                {t('cancel')}
              </Button>
              <Button size="sm" onClick={handleSave}>
                {t('save')}
              </Button>
            </div>
          </div>
        )}
      </SettingsSection>

      <AlertDialog open={deleteIndex !== null} onOpenChange={() => setDeleteIndex(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('delete')}</AlertDialogTitle>
            <AlertDialogDescription>{t('confirmDelete')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>{t('delete')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
});

ExternalAgentsConfig.displayName = 'ExternalAgentsConfig';

export default ExternalAgentsConfig;
