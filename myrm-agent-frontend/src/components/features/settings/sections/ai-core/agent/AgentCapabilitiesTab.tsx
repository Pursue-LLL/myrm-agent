'use client';

import { X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import ProviderIcon from '@/components/features/settings/model-service/ProviderIcon';
import ModelPickerPopover from '@/components/features/app-shell/model-picker-popover';
import TemperatureSlider from '@/components/features/settings/default-model/TemperatureSlider';
import AgentConfigCards from '@/components/features/chat-window/agent-config-panel/AgentConfigCards';
import { AgentOpenAPIServicesTab } from './AgentOpenAPIServicesTab';
import { AgentSubagentBinding } from './AgentSubagentBinding';
import { AgentSharedContextBinding } from './AgentSharedContextBinding';
import { AgentNotifyTargets } from './AgentNotifyTargets';
import { AgentBrowserConfigSection } from './AgentBrowserConfigSection';
import { IconChevronDown } from '@/components/features/icons/PremiumIcons';
import type { ConfigCardType } from '@/components/features/chat-window/agent-config-panel/AgentConfigCards';
import type {
  AgentModelSelection,
  AgentSessionPolicy,
  OpenAPIServiceConfig,
  NotifyTarget,
  WorkspacePolicy,
} from '@/services/agent';
import type { Skill } from '@/store/skill/types';
import type { MCPServiceConfig } from '@/store/config/types';
import type { BuiltinToolId } from '@/store/chat/types';

interface AgentCapabilitiesTabProps {
  editor: {
    modelSelection: AgentModelSelection | null;
    setModelSelection: (val: AgentModelSelection) => void;
    maxIterations: number | null;
    setMaxIterations: (val: number | null) => void;
    workspacePolicy: WorkspacePolicy;
    setWorkspacePolicy: (val: WorkspacePolicy) => void;
    engineParams: Record<string, unknown> | null;
    setEngineParams: (val: Record<string, unknown>) => void;
    browserEngine?: string;
    setBrowserEngine: (val: string | undefined) => void;
    browserSource?: string;
    setBrowserSource: (val: string | undefined) => void;
    dialogPolicy?: string;
    setDialogPolicy: (val: string | undefined) => void;
    sessionRecording?: string;
    setSessionRecording: (val: string | undefined) => void;
    sessionPolicy: AgentSessionPolicy | null;
    setSessionPolicy: (val: AgentSessionPolicy | null) => void;
    selectedSkillDetails: Skill[];
    selectedMcpDetails: MCPServiceConfig[];
    systemPrompt: string;
    useGlobalInstruction: boolean;
    enabledBuiltinTools: BuiltinToolId[];
    isReadonly: boolean;
    setEditDialogType: (type: ConfigCardType) => void;
    setEditDialogOpen: (open: boolean) => void;
    openapiServices: OpenAPIServiceConfig[];
    setOpenapiServices: (val: OpenAPIServiceConfig[]) => void;
    selectedSubagentIds: string[];
    setSelectedSubagentIds: (val: string[]) => void;
    notifyTargets: NotifyTarget[];
    setNotifyTargets: (val: NotifyTarget[]) => void;
  };
  agentId: string | null;
  isNew: boolean;
}

export function AgentCapabilitiesTab({ editor, agentId, isNew }: AgentCapabilitiesTabProps) {
  const t = useTranslations();

  return (
    <div
      className={cn(
        'space-y-4',
        'animate-in fade-in-50 duration-300',
        editor.isReadonly && 'pointer-events-none opacity-70',
      )}
    >
      <ModelBindingSection editor={editor} t={t} />
      {editor.modelSelection && <ModelParamsSection editor={editor} t={t} />}
      <MaxIterationsSection editor={editor} t={t} />
      <WorkspacePolicySection editor={editor} t={t} />
      <ParallelFissionSection editor={editor} t={t} />
      <AdvancedEngineParamsSection editor={editor} t={t} />
      <ConsensusSection editor={editor} t={t} />

      <AgentBrowserConfigSection
        browserEngine={editor.browserEngine}
        onBrowserEngineChange={editor.setBrowserEngine}
        browserSource={editor.browserSource}
        onBrowserSourceChange={editor.setBrowserSource}
        dialogPolicy={editor.dialogPolicy}
        onDialogPolicyChange={editor.setDialogPolicy}
        sessionRecording={editor.sessionRecording}
        onSessionRecordingChange={editor.setSessionRecording}
      />

      <SessionPolicySection editor={editor} t={t} />

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
  );
}

/* ─── sub-sections ─── */

type SectionProps = {
  editor: AgentCapabilitiesTabProps['editor'];
  t: ReturnType<typeof useTranslations>;
};

function ModelBindingSection({ editor, t }: SectionProps) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-foreground">{t('agent.modelBinding')}</h3>
        <p className="text-xs text-muted-foreground mt-0.5">{t('agent.modelBindingDesc')}</p>
      </div>
      <ModelPickerPopover
        currentSelection={editor.modelSelection}
        onSelect={(providerId, model) =>
          editor.setModelSelection({ ...editor.modelSelection, providerId, model })
        }
        fallbackSelection={
          editor.modelSelection?.fallbackProviderId && editor.modelSelection?.fallbackModel
            ? { providerId: editor.modelSelection.fallbackProviderId, model: editor.modelSelection.fallbackModel }
            : null
        }
        onSelectFallback={(providerId, model) =>
          editor.setModelSelection({ ...editor.modelSelection!, fallbackProviderId: providerId, fallbackModel: model })
        }
        onClearFallback={() =>
          editor.setModelSelection({ ...editor.modelSelection!, fallbackProviderId: undefined, fallbackModel: undefined })
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
  );
}

function ModelParamsSection({ editor, t }: SectionProps) {
  const ms = editor.modelSelection!;
  const kwargs = ms.modelKwargs ?? {};
  const setKwarg = (key: string, val: unknown) => {
    editor.setModelSelection({ ...ms, modelKwargs: { ...kwargs, [key]: val } });
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-foreground">{t('agent.modelParams')}</h3>
        <p className="text-xs text-muted-foreground mt-0.5">{t('agent.modelParamsDesc')}</p>
      </div>
      <div className="space-y-5">
        <TemperatureSlider
          value={(kwargs.temperature as number) ?? 0.7}
          onChange={(val) => setKwarg('temperature', val)}
          label={t('agent.temperature')}
          minLabel={t('agent.precise')}
          maxLabel={t('agent.creative')}
          hint={t('agent.temperatureDesc')}
        />
        <TemperatureSlider
          value={(kwargs.top_p as number) ?? 1.0}
          onChange={(val) => setKwarg('top_p', val)}
          min={0} max={1} step={0.05}
          label={t('agent.topP')}
          minLabel={t('agent.focused')}
          maxLabel={t('agent.diverse')}
          hint={t('agent.topPDesc')}
        />
        <div>
          <label className="text-sm font-medium text-foreground">{t('agent.maxTokens')}</label>
          <p className="text-xs text-muted-foreground mt-0.5 mb-2">{t('agent.maxTokensDesc')}</p>
          <Input
            type="number" min={1} max={128000}
            placeholder={t('agent.maxTokensPlaceholder')}
            value={(kwargs.max_tokens as number) ?? ''}
            onChange={(e) => {
              const val = e.target.value;
              setKwarg('max_tokens', val === '' ? undefined : Math.max(1, parseInt(val, 10) || 1));
            }}
            className="w-full"
          />
        </div>
      </div>
    </div>
  );
}

function MaxIterationsSection({ editor, t }: SectionProps) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-foreground">{t('agent.maxIterations')}</h3>
        <p className="text-xs text-muted-foreground mt-0.5">{t('agent.maxIterationsDesc')}</p>
      </div>
      <Input
        type="number" min={5} max={500}
        placeholder={t('agent.maxIterationsPlaceholder')}
        value={editor.maxIterations ?? ''}
        onChange={(e) => {
          const val = e.target.value;
          editor.setMaxIterations(val === '' ? null : Math.max(5, Math.min(500, parseInt(val, 10) || 5)));
        }}
        className="w-full"
      />
    </div>
  );
}

function WorkspacePolicySection({ editor, t }: SectionProps) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-foreground">{t('agent.workspacePolicy')}</h3>
        <p className="text-xs text-muted-foreground mt-0.5">{t('agent.workspacePolicyDesc')}</p>
      </div>
      <div className="flex flex-col sm:flex-row gap-2">
        {(['INHERIT_REQUESTER', 'ISOLATED_COPY', 'READ_ONLY_SANDBOX'] as const).map((policy) => (
          <button
            key={policy} type="button" disabled={editor.isReadonly}
            className={cn(
              'flex-1 px-3 py-2 rounded-lg border text-xs font-medium transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              editor.workspacePolicy === policy
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border bg-background text-muted-foreground hover:bg-muted',
            )}
            onClick={() => editor.setWorkspacePolicy(policy)}
          >
            {t(`agent.workspacePolicyOption.${policy}`)}
          </button>
        ))}
      </div>
    </div>
  );
}

function ParallelFissionSection({ editor, t }: SectionProps) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-foreground">{t('agent.maxParallelFission')}</h3>
        <p className="text-xs text-muted-foreground mt-0.5">{t('agent.maxParallelFissionDesc')}</p>
      </div>
      <Input
        type="number" min={1} max={5}
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
  );
}

function AdvancedEngineParamsSection({ editor, t }: SectionProps) {
  const ep = editor.engineParams ?? {};
  const setEP = (key: string, val: unknown) => editor.setEngineParams({ ...ep, [key]: val });

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-foreground">{t('agent.advancedEngineParams', { fallback: 'Advanced Engine Parameters' })}</h3>
        <p className="text-xs text-muted-foreground mt-0.5">{t('agent.advancedEngineParamsDesc', { fallback: 'Configure internal engine limits and topology toggles' })}</p>
      </div>
      <div className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[
            { key: 'max_tool_calls', def: '30', min: 1 },
            { key: 'max_bash_calls', def: '15', min: 1 },
            { key: 'max_replan_attempts', def: '3', min: 0 },
            { key: 'timeout_seconds', def: undefined, min: 1 },
          ].map(({ key, def, min }) => (
            <div key={key}>
              <label className="text-xs font-medium text-muted-foreground">{key}</label>
              <Input
                type="number" min={min}
                placeholder={def ? t('agent.engineParam.defaultValue', { value: def }) : t('agent.engineParam.defaultNone')}
                value={(ep[key] as number) ?? ''}
                onChange={(e) => {
                  const val = e.target.value;
                  setEP(key, val === '' ? undefined : parseInt(val, 10));
                }}
                className="w-full mt-1"
              />
            </div>
          ))}
        </div>

        <div className="pt-2 border-t border-border/50 grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[
            { key: 'enable_replan', label: 'enableReplan', desc: 'enableReplanDesc', defaultVal: true, invert: false },
            { key: 'enable_context_compression', label: 'contextCompression', desc: 'contextCompressionDesc', defaultVal: true, invert: false },
            { key: 'enable_parallel_tool_calls', label: 'parallelToolCalls', desc: 'parallelToolCallsDesc', defaultVal: true, invert: false },
            { key: 'adversarial_verification', label: 'adversarialVerifier', desc: 'adversarialVerifierDesc', defaultVal: false, invert: false },
          ].map(({ key, label, desc, defaultVal }) => (
            <div key={key} className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-foreground">{t(`agent.engineParam.${label}`)}</label>
                <p className="text-xs text-muted-foreground">{t(`agent.engineParam.${desc}`)}</p>
              </div>
              <Switch
                checked={defaultVal ? ep[key] !== false : ep[key] === true}
                onCheckedChange={(checked) => setEP(key, checked)}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ConsensusSection({ editor, t }: SectionProps) {
  const ep = editor.engineParams ?? {};
  const consensus = (ep.consensus as Record<string, unknown>) ?? {};
  const isEnabled = !!consensus.enabled;

  const setConsensus = (patch: Record<string, unknown>) => {
    editor.setEngineParams({ ...ep, consensus: { ...consensus, ...patch } });
  };

  return (
    <div className="rounded-xl bg-card/60 border border-border/50 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-medium text-foreground">{t('agent.consensusTitle')}</h4>
          <p className="text-xs text-muted-foreground mt-0.5">{t('agent.consensusDesc')}</p>
        </div>
        <Switch
          checked={isEnabled}
          onCheckedChange={(checked) => {
            setConsensus(checked ? {
              enabled: true,
              reference_temperature: consensus.reference_temperature ?? 0.6,
              aggregator_temperature: consensus.aggregator_temperature ?? 0.4,
              min_successful: consensus.min_successful ?? 1,
              timeout_per_model: consensus.timeout_per_model ?? 120,
              timeout_total: consensus.timeout_total ?? 300,
              reference_model_selections: consensus.reference_model_selections ?? [],
              aggregator_model_selection: consensus.aggregator_model_selection ?? null,
            } : { ...consensus, enabled: false });
          }}
        />
      </div>
      {isEnabled && (
        <div className="space-y-4 pt-2 border-t border-border/30">
          <ConsensusRefModels consensus={consensus} setConsensus={setConsensus} t={t} />
          <ConsensusAggModel consensus={consensus} setConsensus={setConsensus} t={t} />
          <div className="grid grid-cols-2 gap-3">
            {[
              { key: 'reference_temperature', label: 'consensusRefTemp', def: 0.6, min: 0, max: 2, step: 0.1 },
              { key: 'aggregator_temperature', label: 'consensusAggTemp', def: 0.4, min: 0, max: 2, step: 0.1 },
            ].map(({ key, label, def, min, max, step }) => (
              <div key={key}>
                <label className="text-xs font-medium text-muted-foreground">{t(`agent.${label}`)}</label>
                <Input
                  type="number" min={min} max={max} step={step}
                  value={(consensus[key] as number) ?? def}
                  onChange={(e) => setConsensus({ [key]: parseFloat(e.target.value) || def })}
                  className="w-full mt-1"
                />
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('agent.consensusMinSuccessful')}</label>
              <Input type="number" min={1} max={10} value={(consensus.min_successful as number) ?? 1}
                onChange={(e) => setConsensus({ min_successful: parseInt(e.target.value, 10) || 1 })} className="w-full mt-1" />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('agent.consensusTimeout')}</label>
              <Input type="number" min={10} max={600} value={(consensus.timeout_total as number) ?? 300}
                onChange={(e) => setConsensus({ timeout_total: parseInt(e.target.value, 10) || 300 })} className="w-full mt-1" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ConsensusRefModels({ consensus, setConsensus, t }: { consensus: Record<string, unknown>; setConsensus: (p: Record<string, unknown>) => void; t: ReturnType<typeof useTranslations> }) {
  const refs = (consensus.reference_model_selections as Array<{ providerId: string; model: string }>) ?? [];
  return (
    <div>
      <label className="text-xs font-medium text-muted-foreground">{t('agent.consensusRefModels')}</label>
      <p className="text-[10px] text-muted-foreground/70 mt-0.5">{t('agent.consensusRefModelsDesc')}</p>
      <div className="flex flex-wrap gap-1.5 mt-2">
        {refs.map((sel, idx) => (
          <div key={`${sel.providerId}-${sel.model}-${idx}`} className="flex items-center gap-1.5 rounded-lg bg-muted/50 border border-border/40 px-2.5 py-1.5 text-xs group">
            <ProviderIcon providerId={sel.providerId} size={14} />
            <span className="text-foreground/80 max-w-[120px] truncate">{sel.model}</span>
            <button type="button" className="ml-0.5 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
              onClick={() => { const next = [...refs]; next.splice(idx, 1); setConsensus({ reference_model_selections: next }); }}>
              <X size={12} />
            </button>
          </div>
        ))}
        <ModelPickerPopover
          trigger={
            <button type="button" className="flex items-center gap-1 rounded-lg border border-dashed border-border/60 px-2.5 py-1.5 text-xs text-muted-foreground hover:border-primary/40 hover:text-primary transition-colors">
              <span>+</span><span>{t('agent.consensusAddModel')}</span>
            </button>
          }
          onSelect={(providerId, model) => {
            if (!refs.some((r) => r.providerId === providerId && r.model === model)) {
              setConsensus({ reference_model_selections: [...refs, { providerId, model }] });
            }
          }}
        />
      </div>
      {refs.length === 0 && <p className="text-[10px] text-amber-500/80 mt-1.5">{t('agent.consensusNoModels')}</p>}
    </div>
  );
}

function ConsensusAggModel({ consensus, setConsensus, t }: { consensus: Record<string, unknown>; setConsensus: (p: Record<string, unknown>) => void; t: ReturnType<typeof useTranslations> }) {
  const aggSel = consensus.aggregator_model_selection as { providerId: string; model: string } | null | undefined;
  return (
    <div>
      <label className="text-xs font-medium text-muted-foreground">{t('agent.consensusAggModel')}</label>
      <p className="text-[10px] text-muted-foreground/70 mt-0.5">{t('agent.consensusAggModelDesc')}</p>
      <div className="flex items-center gap-2 mt-2">
        {aggSel?.providerId && aggSel?.model ? (
          <div className="flex items-center gap-1.5 rounded-lg bg-muted/50 border border-border/40 px-2.5 py-1.5 text-xs group">
            <ProviderIcon providerId={aggSel.providerId} size={14} />
            <span className="text-foreground/80 max-w-[140px] truncate">{aggSel.model}</span>
            <button type="button" className="ml-0.5 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
              onClick={() => setConsensus({ aggregator_model_selection: null })}>
              <X size={12} />
            </button>
          </div>
        ) : (
          <span className="text-[10px] text-muted-foreground/60">{t('agent.consensusUsingPrimary')}</span>
        )}
        <ModelPickerPopover
          trigger={
            <button type="button" className="flex items-center gap-1 rounded-lg border border-dashed border-border/60 px-2 py-1 text-[11px] text-muted-foreground hover:border-primary/40 hover:text-primary transition-colors">
              <span>+</span>
            </button>
          }
          currentSelection={aggSel ?? undefined}
          onSelect={(providerId, model) => setConsensus({ aggregator_model_selection: { providerId, model } })}
        />
      </div>
    </div>
  );
}

function SessionPolicySection({ editor, t }: SectionProps) {
  return (
    <div className="rounded-xl bg-card/60 border border-border/50 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-medium text-foreground">{t('agent.sessionPolicy')}</h4>
          <p className="text-xs text-muted-foreground mt-0.5">{t('agent.sessionPolicyDesc')}</p>
        </div>
        <Switch
          checked={editor.sessionPolicy !== null}
          onCheckedChange={(checked) => {
            editor.setSessionPolicy(checked ? { mode: 'daily', daily_reset_hour: 4, idle_minutes: 120 } : null);
          }}
        />
      </div>
      {editor.sessionPolicy && (
        <div className="space-y-3 pt-2 border-t border-border/30">
          <div>
            <label className="text-xs font-medium text-muted-foreground">{t('agent.sessionPolicyMode')}</label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-1.5">
              {(['persistent', 'daily', 'idle'] as const).map((mode) => (
                <button key={mode} type="button"
                  className={cn(
                    'rounded-lg border px-3 py-2 text-xs transition-all',
                    editor.sessionPolicy?.mode === mode
                      ? 'border-primary bg-primary/10 text-primary font-medium'
                      : 'border-border/50 bg-card/30 text-muted-foreground hover:border-primary/30',
                  )}
                  onClick={() => editor.setSessionPolicy({ ...editor.sessionPolicy!, mode })}>
                  <span className="block font-medium">{t(`agent.sessionPolicy${mode.charAt(0).toUpperCase() + mode.slice(1)}` as 'agent.sessionPolicyPersistent')}</span>
                  <span className="block text-[10px] mt-0.5 opacity-70">{t(`agent.sessionPolicy${mode.charAt(0).toUpperCase() + mode.slice(1)}Desc` as 'agent.sessionPolicyPersistentDesc')}</span>
                </button>
              ))}
            </div>
          </div>
          {editor.sessionPolicy.mode === 'daily' && (
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('agent.sessionPolicyResetHour')}</label>
              <Input type="number" min={0} max={23}
                value={editor.sessionPolicy.daily_reset_hour}
                onChange={(e) => editor.setSessionPolicy({ ...editor.sessionPolicy!, daily_reset_hour: Math.max(0, Math.min(23, parseInt(e.target.value, 10) || 0)) })}
                className="w-full mt-1" />
            </div>
          )}
          {editor.sessionPolicy.mode === 'idle' && (
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('agent.sessionPolicyIdleMinutes')}</label>
              <Input type="number" min={1} max={10080}
                value={editor.sessionPolicy.idle_minutes}
                onChange={(e) => editor.setSessionPolicy({ ...editor.sessionPolicy!, idle_minutes: Math.max(1, Math.min(10080, parseInt(e.target.value, 10) || 120)) })}
                className="w-full mt-1" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
