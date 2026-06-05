'use client';

import { useState, useMemo } from 'react';
import { X, Sparkles } from 'lucide-react';
import { useTranslations } from 'next-intl';
import {
  IconArrowRight,
  IconFileText,
  IconZap,
  IconBot,
  IconChevronDown,
  IconShield,
} from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { useAgentEditor } from '@/hooks/useAgentEditor';
import { AgentBasicInfoTab } from './agent/AgentBasicInfoTab';
import { AgentPreviewCard } from './agent/AgentPreviewCard';
import AgentConfigCards from '@/components/features/chat-window/agent-config-panel/AgentConfigCards';
import AgentConfigEditDialog from '@/components/features/chat-window/agent-config-panel/AgentConfigEditDialog';
import ProviderIcon from '@/components/features/settings/model-service/ProviderIcon';
import ModelPickerPopover from '@/components/features/app-shell/model-picker-popover';
import TemperatureSlider from '@/components/features/settings/default-model/TemperatureSlider';
import { AgentSecurityTab } from './agent/AgentSecurityTab';
import { AgentSecretsTab } from './agent/AgentSecretsTab';
import { AgentSharedContextBinding } from './agent/AgentSharedContextBinding';
import { AgentSubagentBinding } from './agent/AgentSubagentBinding';
import { AgentProfileTimeMachine } from './agent/AgentProfileTimeMachine';
import { AgentNotifyTargets } from './agent/AgentNotifyTargets';
import { AgentOpenAPIServicesTab } from './agent/AgentOpenAPIServicesTab';
import { AgentInstinctInboxTab } from './agent/AgentInstinctInboxTab';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import { IconKey } from '@/components/features/icons/PremiumIcons';
import { exportAgent } from '@/services/agent';
import { toast } from '@/hooks/useToast';

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
        store.fetchAgents(1, 20, true);
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
      a.download = `${data.name || 'agent'}.agent.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast({ title: t('agent.exportSuccess') });
    } catch (e) {
      console.error('Failed to export agent:', e);
      toast({ title: t('agent.exportFailed'), variant: 'destructive' });
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

          {activeTab === 'capabilities' && (
            <div
              className={cn(
                'space-y-4',
                'animate-in fade-in-50 duration-300',
                editor.isReadonly && 'pointer-events-none opacity-70',
              )}
            >
              <div className="rounded-xl border border-border bg-card p-4">
                <div className="mb-3">
                  <h3 className="text-sm font-medium text-foreground">{t('agent.modelBinding')}</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">{t('agent.modelBindingDesc')}</p>
                </div>

                <ModelPickerPopover
                  currentSelection={editor.modelSelection}
                  onSelect={(providerId, model) =>
                    editor.setModelSelection({
                      ...editor.modelSelection,
                      providerId,
                      model,
                    })
                  }
                  fallbackSelection={
                    editor.modelSelection?.fallbackProviderId && editor.modelSelection?.fallbackModel
                      ? {
                          providerId: editor.modelSelection.fallbackProviderId,
                          model: editor.modelSelection.fallbackModel,
                        }
                      : null
                  }
                  onSelectFallback={(providerId, model) =>
                    editor.setModelSelection({
                      ...editor.modelSelection!,
                      fallbackProviderId: providerId,
                      fallbackModel: model,
                    })
                  }
                  onClearFallback={() =>
                    editor.setModelSelection({
                      ...editor.modelSelection!,
                      fallbackProviderId: undefined,
                      fallbackModel: undefined,
                    })
                  }
                  trigger={
                    <button
                      type="button"
                      className={cn(
                        'flex h-9 w-full items-center justify-between rounded-lg border px-3 py-2 text-sm transition-colors',
                        editor.modelSelection
                          ? 'border-primary/20 bg-primary/5'
                          : 'border-input bg-secondary/50 text-muted-foreground hover:bg-secondary/80',
                      )}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        {editor.modelSelection && (
                          <ProviderIcon providerId={editor.modelSelection.providerId} size={14} />
                        )}
                        <span className="truncate">{editor.modelSelection?.model ?? t('agent.useDefaultModel')}</span>
                      </div>
                      <IconChevronDown className="h-4 w-4 opacity-50 shrink-0 ml-2" />
                    </button>
                  }
                />
              </div>

              {editor.modelSelection && (
                <div className="rounded-xl border border-border bg-card p-4">
                  <div className="mb-3">
                    <h3 className="text-sm font-medium text-foreground">{t('agent.modelParams')}</h3>
                    <p className="text-xs text-muted-foreground mt-0.5">{t('agent.modelParamsDesc')}</p>
                  </div>
                  <div className="space-y-5">
                    <TemperatureSlider
                      value={(editor.modelSelection.modelKwargs?.temperature as number) ?? 0.7}
                      onChange={(val) =>
                        editor.setModelSelection({
                          ...editor.modelSelection!,
                          modelKwargs: { ...editor.modelSelection!.modelKwargs, temperature: val },
                        })
                      }
                      label={t('agent.temperature')}
                      minLabel={t('agent.precise')}
                      maxLabel={t('agent.creative')}
                      hint={t('agent.temperatureDesc')}
                    />
                    <TemperatureSlider
                      value={(editor.modelSelection.modelKwargs?.top_p as number) ?? 1.0}
                      onChange={(val) =>
                        editor.setModelSelection({
                          ...editor.modelSelection!,
                          modelKwargs: { ...editor.modelSelection!.modelKwargs, top_p: val },
                        })
                      }
                      min={0}
                      max={1}
                      step={0.05}
                      label={t('agent.topP')}
                      minLabel={t('agent.focused')}
                      maxLabel={t('agent.diverse')}
                      hint={t('agent.topPDesc')}
                    />
                    <div>
                      <label className="text-sm font-medium text-foreground">{t('agent.maxTokens')}</label>
                      <p className="text-xs text-muted-foreground mt-0.5 mb-2">{t('agent.maxTokensDesc')}</p>
                      <Input
                        type="number"
                        min={1}
                        max={128000}
                        placeholder={t('agent.maxTokensPlaceholder')}
                        value={(editor.modelSelection.modelKwargs?.max_tokens as number) ?? ''}
                        onChange={(e) => {
                          const val = e.target.value;
                          editor.setModelSelection({
                            ...editor.modelSelection!,
                            modelKwargs: {
                              ...editor.modelSelection!.modelKwargs,
                              max_tokens: val === '' ? undefined : Math.max(1, parseInt(val, 10) || 1),
                            },
                          });
                        }}
                        className="w-full"
                      />
                    </div>
                  </div>
                </div>
              )}

              <div className="rounded-xl border border-border bg-card p-4">
                <div className="mb-3">
                  <h3 className="text-sm font-medium text-foreground">{t('agent.maxIterations')}</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">{t('agent.maxIterationsDesc')}</p>
                </div>
                <Input
                  type="number"
                  min={5}
                  max={500}
                  placeholder={t('agent.maxIterationsPlaceholder')}
                  value={editor.maxIterations ?? ''}
                  onChange={(e) => {
                    const val = e.target.value;
                    editor.setMaxIterations(val === '' ? null : Math.max(5, Math.min(500, parseInt(val, 10) || 5)));
                  }}
                  className="w-full"
                />
              </div>

              <div className="rounded-xl border border-border bg-card p-4">
                <div className="mb-3">
                  <h3 className="text-sm font-medium text-foreground">{t('agent.maxParallelFission')}</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">{t('agent.maxParallelFissionDesc')}</p>
                </div>
                <Input
                  type="number"
                  min={1}
                  max={5}
                  placeholder={t('agent.maxParallelFissionPlaceholder')}
                  value={(editor.engineParams?.max_parallel_fission as number) ?? ''}
                  onChange={(e) => {
                    const val = e.target.value;
                    editor.setEngineParams({
                      ...editor.engineParams,
                      max_parallel_fission: val === '' ? undefined : Math.max(1, Math.min(5, parseInt(val, 10) || 3)),
                    });
                  }}
                  className="w-full"
                />
              </div>

              <div className="rounded-xl border border-border bg-card p-4">
                <div className="mb-3">
                  <h3 className="text-sm font-medium text-foreground">
                    {t('agent.advancedEngineParams', { fallback: 'Advanced Engine Parameters' })}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {t('agent.advancedEngineParamsDesc', {
                      fallback: 'Configure internal engine limits and topology toggles',
                    })}
                  </p>
                </div>
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">max_tool_calls</label>
                      <Input
                        type="number"
                        min={1}
                        placeholder="Default: 30"
                        value={(editor.engineParams?.max_tool_calls as number) ?? ''}
                        onChange={(e) => {
                          const val = e.target.value;
                          editor.setEngineParams({
                            ...editor.engineParams,
                            max_tool_calls: val === '' ? undefined : parseInt(val, 10),
                          });
                        }}
                        className="w-full mt-1"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">max_bash_calls</label>
                      <Input
                        type="number"
                        min={1}
                        placeholder="Default: 15"
                        value={(editor.engineParams?.max_bash_calls as number) ?? ''}
                        onChange={(e) => {
                          const val = e.target.value;
                          editor.setEngineParams({
                            ...editor.engineParams,
                            max_bash_calls: val === '' ? undefined : parseInt(val, 10),
                          });
                        }}
                        className="w-full mt-1"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">max_replan_attempts</label>
                      <Input
                        type="number"
                        min={0}
                        placeholder="Default: 3"
                        value={(editor.engineParams?.max_replan_attempts as number) ?? ''}
                        onChange={(e) => {
                          const val = e.target.value;
                          editor.setEngineParams({
                            ...editor.engineParams,
                            max_replan_attempts: val === '' ? undefined : parseInt(val, 10),
                          });
                        }}
                        className="w-full mt-1"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">timeout_seconds</label>
                      <Input
                        type="number"
                        min={1}
                        placeholder="Default: None"
                        value={(editor.engineParams?.timeout_seconds as number) ?? ''}
                        onChange={(e) => {
                          const val = e.target.value;
                          editor.setEngineParams({
                            ...editor.engineParams,
                            timeout_seconds: val === '' ? undefined : parseInt(val, 10),
                          });
                        }}
                        className="w-full mt-1"
                      />
                    </div>
                  </div>

                  <div className="pt-2 border-t border-border/50 grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <label className="text-sm font-medium text-foreground">Enable Replan</label>
                        <p className="text-xs text-muted-foreground">Allow agent to self-correct tool errors</p>
                      </div>
                      <Switch
                        checked={editor.engineParams?.enable_replan !== false}
                        onCheckedChange={(checked) => {
                          editor.setEngineParams({
                            ...editor.engineParams,
                            enable_replan: checked,
                          });
                        }}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <label className="text-sm font-medium text-foreground">Context Compression</label>
                        <p className="text-xs text-muted-foreground">Auto-compress long context history</p>
                      </div>
                      <Switch
                        checked={editor.engineParams?.enable_context_compression !== false}
                        onCheckedChange={(checked) => {
                          editor.setEngineParams({
                            ...editor.engineParams,
                            enable_context_compression: checked,
                          });
                        }}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <label className="text-sm font-medium text-foreground">Parallel Tool Calls</label>
                        <p className="text-xs text-muted-foreground">Allow multiple tools at once</p>
                      </div>
                      <Switch
                        checked={editor.engineParams?.enable_parallel_tool_calls !== false}
                        onCheckedChange={(checked) => {
                          editor.setEngineParams({
                            ...editor.engineParams,
                            enable_parallel_tool_calls: checked,
                          });
                        }}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <label className="text-sm font-medium text-foreground">Adversarial Verifier</label>
                        <p className="text-xs text-muted-foreground">Force physical execution sandbox tests</p>
                      </div>
                      <Switch
                        checked={editor.engineParams?.adversarial_verification === true}
                        onCheckedChange={(checked) => {
                          editor.setEngineParams({
                            ...editor.engineParams,
                            adversarial_verification: checked,
                          });
                        }}
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* MoA Consensus Configuration */}
              <div className="rounded-xl bg-card/60 border border-border/50 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-medium text-foreground">{t('agent.consensusTitle')}</h4>
                    <p className="text-xs text-muted-foreground mt-0.5">{t('agent.consensusDesc')}</p>
                  </div>
                  <Switch
                    checked={!!(editor.engineParams?.consensus as Record<string, unknown>)?.enabled}
                    onCheckedChange={(checked) => {
                      const prev = (editor.engineParams?.consensus as Record<string, unknown>) ?? {};
                      editor.setEngineParams({
                        ...editor.engineParams,
                        consensus: checked
                          ? {
                              enabled: true,
                              reference_temperature: prev.reference_temperature ?? 0.6,
                              aggregator_temperature: prev.aggregator_temperature ?? 0.4,
                              min_successful: prev.min_successful ?? 1,
                              timeout_per_model: prev.timeout_per_model ?? 120,
                              timeout_total: prev.timeout_total ?? 300,
                              reference_model_selections: prev.reference_model_selections ?? [],
                              aggregator_model_selection: prev.aggregator_model_selection ?? null,
                            }
                          : { ...prev, enabled: false },
                      });
                    }}
                  />
                </div>
                {!!(editor.engineParams?.consensus as Record<string, unknown>)?.enabled && (
                  <div className="space-y-4 pt-2 border-t border-border/30">
                    {/* Reference Models Selector */}
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">
                        {t('agent.consensusRefModels')}
                      </label>
                      <p className="text-[10px] text-muted-foreground/70 mt-0.5">{t('agent.consensusRefModelsDesc')}</p>
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {(
                          ((editor.engineParams?.consensus as Record<string, unknown>)
                            ?.reference_model_selections as Array<{ providerId: string; model: string }>) ?? []
                        ).map((sel, idx) => (
                          <div
                            key={`${sel.providerId}-${sel.model}-${idx}`}
                            className="flex items-center gap-1.5 rounded-lg bg-muted/50 border border-border/40 px-2.5 py-1.5 text-xs group"
                          >
                            <ProviderIcon providerId={sel.providerId} size={14} />
                            <span className="text-foreground/80 max-w-[120px] truncate">{sel.model}</span>
                            <button
                              type="button"
                              className="ml-0.5 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                              onClick={() => {
                                const consensus = (editor.engineParams?.consensus as Record<string, unknown>) ?? {};
                                const refs = [
                                  ...((consensus.reference_model_selections as Array<{
                                    providerId: string;
                                    model: string;
                                  }>) ?? []),
                                ];
                                refs.splice(idx, 1);
                                editor.setEngineParams({
                                  ...editor.engineParams,
                                  consensus: { ...consensus, reference_model_selections: refs },
                                });
                              }}
                            >
                              <X size={12} />
                            </button>
                          </div>
                        ))}
                        <ModelPickerPopover
                          trigger={
                            <button
                              type="button"
                              className="flex items-center gap-1 rounded-lg border border-dashed border-border/60 px-2.5 py-1.5 text-xs text-muted-foreground hover:border-primary/40 hover:text-primary transition-colors"
                            >
                              <span>+</span>
                              <span>{t('agent.consensusAddModel')}</span>
                            </button>
                          }
                          onSelect={(providerId, model) => {
                            const consensus = (editor.engineParams?.consensus as Record<string, unknown>) ?? {};
                            const refs = [
                              ...((consensus.reference_model_selections as Array<{
                                providerId: string;
                                model: string;
                              }>) ?? []),
                            ];
                            const exists = refs.some((r) => r.providerId === providerId && r.model === model);
                            if (!exists) {
                              refs.push({ providerId, model });
                              editor.setEngineParams({
                                ...editor.engineParams,
                                consensus: { ...consensus, reference_model_selections: refs },
                              });
                            }
                          }}
                        />
                      </div>
                      {(
                        ((editor.engineParams?.consensus as Record<string, unknown>)
                          ?.reference_model_selections as Array<unknown>) ?? []
                      ).length === 0 && (
                        <p className="text-[10px] text-amber-500/80 mt-1.5">{t('agent.consensusNoModels')}</p>
                      )}
                    </div>

                    {/* Aggregator Model Selector */}
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">
                        {t('agent.consensusAggModel')}
                      </label>
                      <p className="text-[10px] text-muted-foreground/70 mt-0.5">{t('agent.consensusAggModelDesc')}</p>
                      <div className="flex items-center gap-2 mt-2">
                        {(() => {
                          const aggSel = (editor.engineParams?.consensus as Record<string, unknown>)
                            ?.aggregator_model_selection as { providerId: string; model: string } | null | undefined;
                          if (aggSel?.providerId && aggSel?.model) {
                            return (
                              <div className="flex items-center gap-1.5 rounded-lg bg-muted/50 border border-border/40 px-2.5 py-1.5 text-xs group">
                                <ProviderIcon providerId={aggSel.providerId} size={14} />
                                <span className="text-foreground/80 max-w-[140px] truncate">{aggSel.model}</span>
                                <button
                                  type="button"
                                  className="ml-0.5 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                                  onClick={() => {
                                    const consensus = (editor.engineParams?.consensus as Record<string, unknown>) ?? {};
                                    editor.setEngineParams({
                                      ...editor.engineParams,
                                      consensus: { ...consensus, aggregator_model_selection: null },
                                    });
                                  }}
                                >
                                  <X size={12} />
                                </button>
                              </div>
                            );
                          }
                          return (
                            <span className="text-[10px] text-muted-foreground/60">
                              {t('agent.consensusUsingPrimary')}
                            </span>
                          );
                        })()}
                        <ModelPickerPopover
                          trigger={
                            <button
                              type="button"
                              className="flex items-center gap-1 rounded-lg border border-dashed border-border/60 px-2 py-1 text-[11px] text-muted-foreground hover:border-primary/40 hover:text-primary transition-colors"
                            >
                              <span>+</span>
                            </button>
                          }
                          currentSelection={
                            ((editor.engineParams?.consensus as Record<string, unknown>)
                              ?.aggregator_model_selection as { providerId: string; model: string } | null) ?? undefined
                          }
                          onSelect={(providerId, model) => {
                            const consensus = (editor.engineParams?.consensus as Record<string, unknown>) ?? {};
                            editor.setEngineParams({
                              ...editor.engineParams,
                              consensus: { ...consensus, aggregator_model_selection: { providerId, model } },
                            });
                          }}
                        />
                      </div>
                    </div>

                    {/* Temperature & Timeout Settings */}
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs font-medium text-muted-foreground">
                          {t('agent.consensusRefTemp')}
                        </label>
                        <Input
                          type="number"
                          min={0}
                          max={2}
                          step={0.1}
                          value={
                            ((editor.engineParams?.consensus as Record<string, unknown>)
                              ?.reference_temperature as number) ?? 0.6
                          }
                          onChange={(e) => {
                            const consensus = (editor.engineParams?.consensus as Record<string, unknown>) ?? {};
                            editor.setEngineParams({
                              ...editor.engineParams,
                              consensus: { ...consensus, reference_temperature: parseFloat(e.target.value) || 0.6 },
                            });
                          }}
                          className="w-full mt-1"
                        />
                      </div>
                      <div>
                        <label className="text-xs font-medium text-muted-foreground">
                          {t('agent.consensusAggTemp')}
                        </label>
                        <Input
                          type="number"
                          min={0}
                          max={2}
                          step={0.1}
                          value={
                            ((editor.engineParams?.consensus as Record<string, unknown>)
                              ?.aggregator_temperature as number) ?? 0.4
                          }
                          onChange={(e) => {
                            const consensus = (editor.engineParams?.consensus as Record<string, unknown>) ?? {};
                            editor.setEngineParams({
                              ...editor.engineParams,
                              consensus: { ...consensus, aggregator_temperature: parseFloat(e.target.value) || 0.4 },
                            });
                          }}
                          className="w-full mt-1"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs font-medium text-muted-foreground">
                          {t('agent.consensusMinSuccessful')}
                        </label>
                        <Input
                          type="number"
                          min={1}
                          max={10}
                          value={
                            ((editor.engineParams?.consensus as Record<string, unknown>)?.min_successful as number) ?? 1
                          }
                          onChange={(e) => {
                            const consensus = (editor.engineParams?.consensus as Record<string, unknown>) ?? {};
                            editor.setEngineParams({
                              ...editor.engineParams,
                              consensus: { ...consensus, min_successful: parseInt(e.target.value, 10) || 1 },
                            });
                          }}
                          className="w-full mt-1"
                        />
                      </div>
                      <div>
                        <label className="text-xs font-medium text-muted-foreground">
                          {t('agent.consensusTimeout')}
                        </label>
                        <Input
                          type="number"
                          min={10}
                          max={600}
                          value={
                            ((editor.engineParams?.consensus as Record<string, unknown>)?.timeout_total as number) ??
                            300
                          }
                          onChange={(e) => {
                            const consensus = (editor.engineParams?.consensus as Record<string, unknown>) ?? {};
                            editor.setEngineParams({
                              ...editor.engineParams,
                              consensus: { ...consensus, timeout_total: parseInt(e.target.value, 10) || 300 },
                            });
                          }}
                          className="w-full mt-1"
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Per-Agent Session Policy */}
              <div className="rounded-xl bg-card/60 border border-border/50 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-medium text-foreground">{t('agent.sessionPolicy')}</h4>
                    <p className="text-xs text-muted-foreground mt-0.5">{t('agent.sessionPolicyDesc')}</p>
                  </div>
                  <Switch
                    checked={editor.sessionPolicy !== null}
                    onCheckedChange={(checked) => {
                      editor.setSessionPolicy(
                        checked ? { mode: 'daily', daily_reset_hour: 4, idle_minutes: 120 } : null,
                      );
                    }}
                  />
                </div>
                {editor.sessionPolicy && (
                  <div className="space-y-3 pt-2 border-t border-border/30">
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">
                        {t('agent.sessionPolicyMode')}
                      </label>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-1.5">
                        {(['persistent', 'daily', 'idle'] as const).map((mode) => (
                          <button
                            key={mode}
                            type="button"
                            className={cn(
                              'rounded-lg border px-3 py-2 text-xs transition-all',
                              editor.sessionPolicy?.mode === mode
                                ? 'border-primary bg-primary/10 text-primary font-medium'
                                : 'border-border/50 bg-card/30 text-muted-foreground hover:border-primary/30',
                            )}
                            onClick={() => editor.setSessionPolicy({ ...editor.sessionPolicy!, mode })}
                          >
                            <span className="block font-medium">
                              {t(
                                `agent.sessionPolicy${mode.charAt(0).toUpperCase() + mode.slice(1)}` as 'agent.sessionPolicyPersistent',
                              )}
                            </span>
                            <span className="block text-[10px] mt-0.5 opacity-70">
                              {t(
                                `agent.sessionPolicy${mode.charAt(0).toUpperCase() + mode.slice(1)}Desc` as 'agent.sessionPolicyPersistentDesc',
                              )}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                    {editor.sessionPolicy.mode === 'daily' && (
                      <div>
                        <label className="text-xs font-medium text-muted-foreground">
                          {t('agent.sessionPolicyResetHour')}
                        </label>
                        <Input
                          type="number"
                          min={0}
                          max={23}
                          value={editor.sessionPolicy.daily_reset_hour}
                          onChange={(e) =>
                            editor.setSessionPolicy({
                              ...editor.sessionPolicy!,
                              daily_reset_hour: Math.max(0, Math.min(23, parseInt(e.target.value, 10) || 0)),
                            })
                          }
                          className="w-full mt-1"
                        />
                      </div>
                    )}
                    {editor.sessionPolicy.mode === 'idle' && (
                      <div>
                        <label className="text-xs font-medium text-muted-foreground">
                          {t('agent.sessionPolicyIdleMinutes')}
                        </label>
                        <Input
                          type="number"
                          min={1}
                          max={10080}
                          value={editor.sessionPolicy.idle_minutes}
                          onChange={(e) =>
                            editor.setSessionPolicy({
                              ...editor.sessionPolicy!,
                              idle_minutes: Math.max(1, Math.min(10080, parseInt(e.target.value, 10) || 120)),
                            })
                          }
                          className="w-full mt-1"
                        />
                      </div>
                    )}
                  </div>
                )}
              </div>

              <AgentConfigCards
                selectedSkills={editor.selectedSkillDetails}
                selectedMcps={editor.selectedMcpDetails}
                systemPrompt={editor.systemPrompt}
                useGlobalInstruction={editor.useGlobalInstruction}
                enabledBuiltinTools={editor.enabledBuiltinTools}
                onCardClick={(type) => {
                  if (editor.isReadonly) return;
                  editor.setEditDialogType(type);
                  editor.setEditDialogOpen(true);
                }}
              />

              <AgentOpenAPIServicesTab
                services={editor.openapiServices}
                onChange={editor.setOpenapiServices}
                readonly={editor.isReadonly}
              />

              <AgentSubagentBinding
                selectedIds={editor.selectedSubagentIds}
                currentAgentId={agentId}
                onChange={editor.setSelectedSubagentIds}
              />

              <AgentSharedContextBinding agentId={agentId} isNew={isNew} />

              <AgentNotifyTargets
                targets={editor.notifyTargets}
                onChange={editor.setNotifyTargets}
                readonly={editor.isReadonly}
              />
            </div>
          )}

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
            <div className={cn(editor.isReadonly && 'pointer-events-none opacity-70')}>
              <AgentInstinctInboxTab agentId={agentId} readonly={editor.isReadonly} />
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
        enabledBuiltinTools={editor.enabledBuiltinTools}
        isSystemPromptHidden={editor.isSystemPromptHidden}
        loadingSystemPrompt={editor.loadingSystemPrompt}
        onShowSystemPrompt={editor.handleShowSystemPrompt}
        onSave={(data) => {
          editor.handleConfigChange(data);
          editor.setEditDialogOpen(false);
        }}
      />
    </div>
  );
}
