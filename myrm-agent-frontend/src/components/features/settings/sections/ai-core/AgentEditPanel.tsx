'use client';

import { useState, useMemo, useCallback } from 'react';
import { Sparkles, Loader2, Wand2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { IconArrowRight, IconFileText, IconZap, IconBot, IconShield } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { useAgentEditor } from '@/hooks/useAgentEditor';
import { AgentBasicInfoTab } from './agent/AgentBasicInfoTab';
import { AgentPreviewCard } from './agent/AgentPreviewCard';
import AgentConfigEditDialog from '@/components/features/chat-window/agent-config-panel/AgentConfigEditDialog';
import { AgentSecurityTab } from './agent/AgentSecurityTab';
import { AgentSecretsTab } from './agent/AgentSecretsTab';
import { AgentProfileTimeMachine } from './agent/AgentProfileTimeMachine';
import { AgentInstinctInboxTab } from './agent/AgentInstinctInboxTab';
import { AgentCapabilitiesTab } from './agent/AgentCapabilitiesTab';
import { IconKey } from '@/components/features/icons/PremiumIcons';
import { AGENT_LIST_BUILTIN_PAGE_SIZE, exportAgent } from '@/services/agent';
import { toast } from '@/hooks/useToast';
import { getApiUrl } from '@/lib/api';
import type { BuiltinToolId } from '@/store/chat/types';
import { Textarea } from '@/components/primitives/textarea';
import { useSkillStore } from '@/store/skill';

type ConfigTab = 'basic' | 'capabilities' | 'security' | 'secrets' | 'inbox';

interface AgentEditPanelProps {
  agentId: string | null;
  isNew?: boolean;
  onBack: () => void;
}

export default function AgentEditPanel({ agentId, isNew = false, onBack }: AgentEditPanelProps) {
  const t = useTranslations();
  const [activeTab, setActiveTab] = useState<ConfigTab>('basic');
  const [exporting, setExporting] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [timeMachineExpanded, setTimeMachineExpanded] = useState(false);

  const editor = useAgentEditor(agentId, isNew, t);

  const fetchMarketSkills = useSkillStore((state) => state.fetchMarketSkills);
  const fetchLocalSkills = useSkillStore((state) => state.fetchLocalSkills);
  const refreshSkills = useCallback(async () => {
    await Promise.all([fetchMarketSkills(), fetchLocalSkills()]);
  }, [fetchMarketSkills, fetchLocalSkills]);

  const [aiIntent, setAiIntent] = useState('');
  const [aiGenerating, setAiGenerating] = useState(false);

  const handleAiBuild = useCallback(
    async (intent: string) => {
      if (!intent.trim() || aiGenerating) return;
      setAiGenerating(true);
      let fullJson = '';
      try {
        const response = await fetch(getApiUrl('/user-agents/ai-build'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ intent, locale: navigator.language || 'en-US' }),
        });
        if (!response.ok) {
          const err = await response.json().catch(() => null);
          throw new Error(err?.detail || `HTTP ${response.status}`);
        }
        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const evt = JSON.parse(line.slice(6));
              if (evt.type === 'content' && typeof evt.data === 'string') {
                fullJson += evt.data;
              }
            } catch {
              /* skip malformed SSE chunks */
            }
          }
        }
        let cleaned = fullJson.trim();
        cleaned = cleaned.replace(/^```(?:json)?\s*\n?/i, '').replace(/\n?\s*```\s*$/i, '');
        const jsonStart = cleaned.indexOf('{');
        const jsonEnd = cleaned.lastIndexOf('}');
        if (jsonStart !== -1 && jsonEnd > jsonStart) cleaned = cleaned.slice(jsonStart, jsonEnd + 1);
        const config = JSON.parse(cleaned);

        if (config.name) editor.setName(config.name);
        if (config.description) editor.setDescription(config.description);

        const validSkillIds = new Set(editor.enabledSkills.map((s) => s.id));
        const validMcpNames = new Set(editor.enabledMcps.map((m) => m.name));
        const validToolIds = new Set(['browser', 'shell_exec', 'code_exec', 'file_ops', 'search', 'image_gen']);

        editor.handleConfigChange({
          ...(config.system_prompt ? { systemPrompt: config.system_prompt } : {}),
          ...(Array.isArray(config.skill_ids)
            ? { selectedSkillIds: (config.skill_ids as string[]).filter((id) => validSkillIds.has(id)) }
            : {}),
          ...(Array.isArray(config.mcp_ids)
            ? { selectedMcpNames: (config.mcp_ids as string[]).filter((id) => validMcpNames.has(id)) }
            : {}),
          ...(Array.isArray(config.builtin_tools)
            ? {
                enabledBuiltinTools: (config.builtin_tools as string[]).filter((id) =>
                  validToolIds.has(id),
                ) as BuiltinToolId[],
              }
            : {}),
        });
        setAiIntent('');
        toast({ title: t('agent.aiBuilder.apply') });
      } catch (e) {
        console.error('AI Build failed:', e);
        toast({
          title: t('agent.aiBuilder.error'),
          description: e instanceof Error ? e.message : undefined,
          variant: 'destructive',
        });
      } finally {
        setAiGenerating(false);
      }
    },
    [aiGenerating, editor, t],
  );

  const handleRollback = async () => {
    if (!agentId) return;
    try {
      setRollingBack(true);
      const { rollbackAgentProfile } = await import('@/services/agent');
      await rollbackAgentProfile(agentId);
      toast({ title: t('agent.rollbackSuccess') });
      await editor.reloadAgent();
      import('@/store/useAgentStore').then((mod) => {
        const store = mod.default.getState();
        store.fetchAgents(1, AGENT_LIST_BUILTIN_PAGE_SIZE, true);
        store.fetchAgent(agentId);
      });
    } catch (e: unknown) {
      console.error('Failed to rollback agent:', e);
      toast({
        title: t('agent.rollbackFailed'),
        description: e instanceof Error ? e.message : undefined,
        variant: 'destructive',
      });
    } finally {
      setRollingBack(false);
    }
  };

  const handleExport = async () => {
    if (!agentId) return;
    try {
      setExporting(true);
      const data = await exportAgent(agentId);

      // 下载 JSON 文件
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const leader = data.leader as Record<string, unknown> | undefined;
      const exportName = (data.name as string) || (leader?.name as string) || 'agent';
      a.download = `${exportName}.agent.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast({ title: t('agent.exportSuccess') });
    } catch (e) {
      console.error('Failed to export agent:', e);
      toast({
        title: t('agent.exportFailed'),
        description: e instanceof Error ? e.message : undefined,
        variant: 'destructive',
      });
    } finally {
      setExporting(false);
    }
  };

  const tabs = useMemo(
    () => [
      {
        id: 'basic' as ConfigTab,
        label: t('agent.basicInfo'),
        icon: IconFileText,
        color: 'text-primary',
      },
      {
        id: 'capabilities' as ConfigTab,
        label: t('agent.capabilities'),
        icon: IconZap,
        color: 'text-emerald-500',
      },
      {
        id: 'security' as ConfigTab,
        label: t('agent.security.tabTitle'),
        icon: IconShield,
        color: 'text-amber-500',
      },
      {
        id: 'secrets' as ConfigTab,
        label: t('agent.secrets.tabTitle', { fallback: 'Secrets' }),
        icon: IconKey,
        color: 'text-rose-500',
      },
      {
        id: 'inbox' as ConfigTab,
        label: t('agent.instinctInbox.tabTitle', { fallback: 'Insights' }),
        icon: Sparkles,
        color: 'text-purple-500',
      },
    ],
    [t],
  );

  const mcpCount = editor.selectedMcpNames.length;
  const skillCount = editor.selectedSkillIds.length + editor.mountedSkillIds.length;

  if (editor.isInitialized && !editor.user) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[70vh] text-center px-4">
        <div className="relative mb-8">
          <div className="absolute inset-0 bg-gradient-to-r from-primary/30 to-violet-500/30 blur-3xl opacity-50" />
          <div className="relative w-24 h-24 rounded-3xl bg-gradient-to-br from-primary/20 to-violet-500/20 border border-primary/20 flex items-center justify-center">
            <IconBot className="w-12 h-12 text-primary" />
          </div>
        </div>
        <h2 className="text-2xl font-bold text-foreground mb-3">{t('agent.loginRequired')}</h2>
        <p className="text-muted-foreground mb-8 max-w-md">{t('agent.loginRequiredDesc')}</p>
        <Button onClick={onBack} variant="outline" className="gap-2 rounded-xl">
          <IconArrowRight className="w-4 h-4 rotate-180" />
          {t('agent.back')}
        </Button>
      </div>
    );
  }

  if (editor.loading) {
    return (
      <div className="flex items-center justify-center min-h-[70vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-16 h-16 rounded-full border-4 border-primary/20 border-t-primary animate-spin" />
          <p className="text-sm text-muted-foreground">{t('agent.loading')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8 space-y-6">
      <div className="flex items-center justify-between">
        <Button
          onClick={onBack}
          variant="ghost"
          className="gap-2 rounded-xl text-muted-foreground hover:text-foreground"
        >
          <IconArrowRight className="w-4 h-4 rotate-180" />
          {t('agent.back')}
        </Button>
        {editor.isReadonly ? (
          <span className="px-3 py-1.5 rounded-lg text-xs font-medium bg-muted/50 text-muted-foreground border border-border/50">
            {t('agent.builtInReadonly')}
          </span>
        ) : !isNew || editor.hasChanges ? (
          <span
            className={cn(
              'px-3 py-1.5 rounded-lg text-xs font-medium',
              editor.hasChanges
                ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20'
                : 'bg-muted/50 text-muted-foreground',
            )}
          >
            {editor.hasChanges ? t('agent.unsaved') : t('agent.saved')}
          </span>
        ) : null}
      </div>

      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold text-foreground">
          {editor.isReadonly ? t('agent.viewAgent') : isNew ? t('agent.createAgent') : t('agent.editAgent')}
        </h1>
        <p className="text-muted-foreground max-w-2xl mx-auto">
          {editor.isReadonly ? t('agent.viewDescription') : t('agent.editDescription')}
        </p>
      </div>

      {isNew && !editor.hasChanges && (
        <div className="rounded-2xl border border-primary/20 bg-gradient-to-r from-primary/5 to-violet-500/5 p-5">
          <div className="flex items-center gap-2 mb-3">
            <Wand2 className="w-5 h-5 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">{t('agent.aiBuilder.title')}</h3>
          </div>
          <p className="text-xs text-muted-foreground mb-3">{t('agent.aiBuilder.subtitle')}</p>
          <div className="flex flex-col sm:flex-row gap-2">
            <Textarea
              value={aiIntent}
              onChange={(e) => setAiIntent(e.target.value)}
              placeholder={t('agent.aiBuilder.placeholder')}
              className="min-h-[60px] max-h-[100px] resize-none text-sm flex-1"
              disabled={aiGenerating}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void handleAiBuild(aiIntent);
                }
              }}
            />
            <Button
              size="sm"
              className="shrink-0 self-end gap-1.5 sm:self-end"
              onClick={() => void handleAiBuild(aiIntent)}
              disabled={!aiIntent.trim() || aiGenerating}
            >
              {aiGenerating ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  {t('agent.aiBuilder.generating')}
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  {t('agent.aiBuilder.apply')}
                </>
              )}
            </Button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-4 order-2 lg:order-1">
          <AgentPreviewCard
            name={editor.name}
            description={editor.description}
            selectedGradient={editor.selectedGradient}
            hasChanges={editor.hasChanges}
            saving={editor.saving}
            exporting={exporting}
            rollingBack={rollingBack}
            snapshotCount={editor.snapshotCount}
            skillCount={skillCount}
            mcpCount={mcpCount}
            readonly={editor.isReadonly}
            onSave={editor.handleSave}
            onStartChat={editor.handleStartChat}
            onExport={!isNew && !editor.isReadonly ? handleExport : undefined}
            onRollback={!isNew && !editor.isReadonly ? handleRollback : undefined}
            onGradientChange={editor.setSelectedGradient}
          />
        </div>

        <div className="lg:col-span-8 order-1 lg:order-2">
          <div className="flex gap-2 mb-6 p-1 rounded-xl bg-muted/50">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  data-testid={`agent-tab-${tab.id}`}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    'flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg',
                    'text-sm font-medium transition-all duration-200',
                    isActive
                      ? 'bg-background text-foreground'
                      : 'text-muted-foreground hover:text-foreground hover:bg-background/50',
                  )}
                >
                  <Icon className={cn('w-4 h-4', isActive ? tab.color : '')} />
                  <span className="hidden sm:inline">{tab.label}</span>
                </button>
              );
            })}
          </div>

          {activeTab === 'basic' && (
            <AgentBasicInfoTab
              name={editor.name}
              description={editor.description}
              personalityStyle={editor.personalityStyle}
              promptMode={editor.promptMode}
              allowDiscovery={editor.allowDiscovery}
              suggestionPrompts={editor.suggestionPrompts}
              readonly={editor.isReadonly}
              onNameChange={editor.setName}
              onDescriptionChange={editor.setDescription}
              onPersonalityChange={editor.setPersonalityStyle}
              onPromptModeChange={editor.setPromptMode}
              onAllowDiscoveryChange={editor.setAllowDiscovery}
              onSuggestionPromptsChange={editor.setSuggestionPrompts}
            />
          )}

          {activeTab === 'capabilities' && <AgentCapabilitiesTab editor={editor} agentId={agentId} isNew={isNew} />}

          {activeTab === 'security' && (
            <div className={cn(editor.isReadonly && 'pointer-events-none opacity-70')}>
              <AgentSecurityTab value={editor.securityOverrides} onChange={editor.setSecurityOverrides} />
            </div>
          )}

          {activeTab === 'secrets' && (
            <div className={cn(editor.isReadonly && 'pointer-events-none opacity-70')}>
              <AgentSecretsTab agentId={agentId} isNew={isNew} />
            </div>
          )}

          {activeTab === 'inbox' && (
            <div>
              <AgentInstinctInboxTab agentId={agentId} />
            </div>
          )}
        </div>
      </div>

      {!isNew && agentId && !editor.isReadonly ? (
        <AgentProfileTimeMachine
          agentId={agentId}
          snapshotCount={editor.snapshotCount}
          onRestored={() => void editor.reloadAgent()}
          expanded={timeMachineExpanded}
          onExpandedChange={setTimeMachineExpanded}
        />
      ) : null}

      <AgentConfigEditDialog
        open={editor.editDialogOpen}
        onOpenChange={editor.setEditDialogOpen}
        type={editor.editDialogType}
        agentId={agentId}
        enabledSkills={editor.enabledSkills}
        enabledMcps={editor.enabledMcps}
        selectedSkillIds={editor.selectedSkillIds}
        mountedSkillIds={editor.mountedSkillIds}
        selectedMcpNames={editor.selectedMcpNames}
        mcpToolSelections={editor.mcpToolSelections}
        systemPrompt={editor.systemPrompt}
        useGlobalInstruction={editor.useGlobalInstruction}
        autoRestoreDomains={editor.autoRestoreDomains}
        browserSource={editor.browserSource}
        dialogPolicy={editor.dialogPolicy}
        sessionRecording={editor.sessionRecording}
        enabledBuiltinTools={editor.enabledBuiltinTools}
        isSystemPromptHidden={editor.isSystemPromptHidden}
        loadingSystemPrompt={editor.loadingSystemPrompt}
        onShowSystemPrompt={editor.handleShowSystemPrompt}
        onSave={(data) => {
          editor.handleConfigChange(data);
          editor.setEditDialogOpen(false);
        }}
        onRefreshSkills={refreshSkills}
      />
    </div>
  );
}
