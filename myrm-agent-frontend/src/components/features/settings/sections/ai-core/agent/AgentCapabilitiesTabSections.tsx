'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import ProviderIcon from '@/components/features/settings/model-service/ProviderIcon';
import ModelPickerPopover from '@/components/features/app-shell/model-picker-popover';
import TemperatureSlider from '@/components/features/settings/default-model/TemperatureSlider';
import { ShieldAlert, X } from 'lucide-react';
import { IconChevronDown } from '@/components/features/icons/PremiumIcons';
import { useManagedPolicyEffective } from '@/hooks/useManagedPolicyEffective';
import { managedPolicyConstraintsForModel } from '@/lib/managedPolicyMatch';
import useProviderStore from '@/store/useProviderStore';
import { ModelSwapContinuityCard } from './ModelSwapContinuityCard';
import type { AgentCapabilitiesTabProps } from './AgentCapabilitiesTab';

type SectionProps = {
  editor: AgentCapabilitiesTabProps['editor'];
  t: ReturnType<typeof useTranslations>;
};

export function ModelBindingSection({ editor, t }: SectionProps) {
  const { policy, active } = useManagedPolicyEffective();
  const defaultModelConfig = useProviderStore((state) => state.defaultModelConfig);
  const boundModelSlug = editor.modelSelection?.model?.trim() ?? '';
  const effectiveModelSlug = boundModelSlug || defaultModelConfig.baseModel.primary?.model?.trim() || '';
  const orgConstraints = useMemo(
    () => (active ? managedPolicyConstraintsForModel(policy, effectiveModelSlug) : null),
    [active, policy, effectiveModelSlug],
  );

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-foreground">{t('agent.modelBinding')}</h3>
        <p className="text-xs text-muted-foreground mt-0.5">{t('agent.modelBindingDesc')}</p>
      </div>
      <ModelPickerPopover
        currentSelection={editor.modelSelection}
        onSelect={(providerId, model) => editor.setModelSelection({ ...editor.modelSelection, providerId, model })}
        fallbackSelection={
          editor.modelSelection?.fallbackProviderId && editor.modelSelection?.fallbackModel
            ? { providerId: editor.modelSelection.fallbackProviderId, model: editor.modelSelection.fallbackModel }
            : null
        }
        onSelectFallback={(providerId, model) =>
          editor.setModelSelection({ ...editor.modelSelection!, fallbackProviderId: providerId, fallbackModel: model })
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
              {editor.modelSelection && <ProviderIcon providerId={editor.modelSelection.providerId} size={14} />}
              <span className="truncate">{editor.modelSelection?.model ?? t('agent.useDefaultModel')}</span>
            </div>
            <IconChevronDown className="h-4 w-4 opacity-50 shrink-0 ml-2" />
          </button>
        }
      />
      {orgConstraints && effectiveModelSlug && (orgConstraints.forceAutoReview || orgConstraints.ignoreAllowlist) && (
        <div className="mt-3 space-y-1.5 rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2">
          <div className="flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
            <ShieldAlert className="h-3.5 w-3.5 shrink-0" />
            <span>{t('agent.orgMapBadgeTitle', { default: 'Organization approval policy' })}</span>
          </div>
          {orgConstraints.forceAutoReview && (
            <p className="text-xs text-muted-foreground">
              {t('agent.orgMapForceReview', {
                default: 'Smart Intent Guard is required for this model.',
              })}
            </p>
          )}
          {orgConstraints.ignoreAllowlist && (
            <p className="text-xs text-muted-foreground">
              {t('agent.orgMapIgnoreAllowlist', {
                default: 'Saved allowlist shortcuts do not apply to this model.',
              })}
            </p>
          )}
          {(orgConstraints.forceAutoReview || orgConstraints.ignoreAllowlist) && (
            <p className="text-xs text-muted-foreground">
              {t('agent.orgMapYoloSuppressed', {
                default: 'YOLO mode will not bypass approvals for this model.',
              })}
            </p>
          )}
        </div>
      )}
      <ModelSwapContinuityCard editor={editor} effectiveModelSlug={effectiveModelSlug} />
    </div>
  );
}

export function ModelParamsSection({ editor, t }: SectionProps) {
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

export function MaxIterationsSection({ editor, t }: SectionProps) {
  return (
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
  );
}

export function WorkspacePolicySection({ editor, t }: SectionProps) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-foreground">{t('agent.workspacePolicy')}</h3>
        <p className="text-xs text-muted-foreground mt-0.5">{t('agent.workspacePolicyDesc')}</p>
      </div>
      <div className="flex flex-col sm:flex-row gap-2">
        {(['INHERIT_REQUESTER', 'ISOLATED_COPY', 'READ_ONLY_SANDBOX'] as const).map((policy) => (
          <button
            key={policy}
            type="button"
            disabled={editor.isReadonly}
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

export function ParallelFissionSection({ editor, t }: SectionProps) {
  return (
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
  );
}

export function IdleCompactSection({ editor, t }: SectionProps) {
  const ep = editor.engineParams ?? {};
  const idleSeconds = typeof ep.idle_compact_after_seconds === 'number' ? ep.idle_compact_after_seconds : 0;
  const enabled = idleSeconds > 0;
  const idleMinutes = enabled ? Math.max(1, Math.round(idleSeconds / 60)) : 30;

  const setEnabled = (nextEnabled: boolean) => {
    if (!nextEnabled) {
      const next: Record<string, unknown> = { ...ep };
      delete next.idle_compact_after_seconds;
      editor.setEngineParams(next);
      return;
    }
    editor.setEngineParams({ ...ep, idle_compact_after_seconds: idleMinutes * 60 });
  };

  const setIdleMinutes = (minutes: number) => {
    const clamped = Math.max(1, Math.min(1440, minutes));
    editor.setEngineParams({ ...ep, idle_compact_after_seconds: clamped * 60 });
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h3 className="text-sm font-medium text-foreground">{t('agent.idleCompact.title')}</h3>
          <p className="text-xs text-muted-foreground">{t('agent.idleCompact.desc')}</p>
        </div>
        <Switch
          checked={enabled}
          onCheckedChange={setEnabled}
          disabled={editor.isReadonly}
          aria-label={t('agent.idleCompact.title')}
        />
      </div>
      {enabled && (
        <div className="mt-4">
          <label className="text-sm font-medium text-foreground">{t('agent.idleCompact.minutes')}</label>
          <p className="text-xs text-muted-foreground mt-0.5 mb-2">{t('agent.idleCompact.minutesDesc')}</p>
          <Input
            type="number"
            min={1}
            max={1440}
            value={idleMinutes}
            onChange={(e) => {
              const parsed = parseInt(e.target.value, 10);
              setIdleMinutes(Number.isFinite(parsed) ? parsed : 30);
            }}
            className="w-full"
          />
        </div>
      )}
      <p className="text-xs text-muted-foreground mt-3">{t('agent.idleCompact.hint')}</p>
    </div>
  );
}

export function AdvancedEngineParamsSection({ editor, t }: SectionProps) {
  const ep = editor.engineParams ?? {};
  const setEP = (key: string, val: unknown) => editor.setEngineParams({ ...ep, [key]: val });

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-foreground">
          {t('agent.advancedEngineParams', { fallback: 'Advanced Engine Parameters' })}
        </h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          {t('agent.advancedEngineParamsDesc', { fallback: 'Configure internal engine limits and topology toggles' })}
        </p>
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
                type="number"
                min={min}
                placeholder={
                  def ? t('agent.engineParam.defaultValue', { value: def }) : t('agent.engineParam.defaultNone')
                }
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
            {
              key: 'enable_context_compression',
              label: 'contextCompression',
              desc: 'contextCompressionDesc',
              defaultVal: true,
              invert: false,
            },
            {
              key: 'enable_parallel_tool_calls',
              label: 'parallelToolCalls',
              desc: 'parallelToolCallsDesc',
              defaultVal: true,
              invert: false,
            },
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

type RoutingMode = 'global' | 'custom' | 'disabled';

function getRoutingMode(ms: AgentCapabilitiesTabProps['editor']['modelSelection']): RoutingMode {
  if (!ms || ms.routingEnabled === undefined) {
    return 'global';
  }
  return ms.routingEnabled ? 'custom' : 'disabled';
}

export function RoutingOverrideSection({ editor, t }: SectionProps) {
  const ms = editor.modelSelection;
  const mode = getRoutingMode(ms);

  const setMode = (next: RoutingMode) => {
    if (!ms) {
      return;
    }
    if (next === 'global') {
      const {
        routingEnabled: _,
        lightProviderId: _lp,
        lightModel: _lm,
        reasoningProviderId: _rp,
        reasoningModel: _rm,
        ...rest
      } = ms;
      editor.setModelSelection(rest);
    } else {
      editor.setModelSelection({ ...ms, routingEnabled: next === 'custom' });
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-foreground">{t('agent.routingOverride')}</h3>
        <p className="text-xs text-muted-foreground mt-0.5">{t('agent.routingOverrideDesc')}</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-2 mb-4">
        {(['global', 'custom', 'disabled'] as const).map((opt) => (
          <button
            key={opt}
            type="button"
            className={cn(
              'flex-1 px-3 py-2 rounded-lg border text-xs font-medium transition-colors text-center',
              mode === opt
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border bg-background text-muted-foreground hover:bg-muted',
            )}
            onClick={() => setMode(opt)}
          >
            {t(`agent.routing${opt === 'global' ? 'UseGlobal' : opt === 'custom' ? 'Custom' : 'Disabled'}`)}
          </button>
        ))}
      </div>

      {mode === 'custom' && ms && (
        <div className="space-y-3 pt-2 border-t border-border/50">
          <RoutingModelSlot
            label={t('agent.routingLightModel')}
            providerId={ms.lightProviderId}
            model={ms.lightModel}
            placeholder={t('agent.routingSelectModel')}
            onSelect={(pid, m) => editor.setModelSelection({ ...ms, lightProviderId: pid, lightModel: m })}
            onClear={() => editor.setModelSelection({ ...ms, lightProviderId: undefined, lightModel: undefined })}
          />
          <RoutingModelSlot
            label={t('agent.routingReasoningModel')}
            providerId={ms.reasoningProviderId}
            model={ms.reasoningModel}
            placeholder={t('agent.routingSelectModel')}
            onSelect={(pid, m) => editor.setModelSelection({ ...ms, reasoningProviderId: pid, reasoningModel: m })}
            onClear={() =>
              editor.setModelSelection({ ...ms, reasoningProviderId: undefined, reasoningModel: undefined })
            }
          />
        </div>
      )}
    </div>
  );
}

function RoutingModelSlot({
  label,
  providerId,
  model,
  placeholder,
  onSelect,
  onClear,
}: {
  label: string;
  providerId?: string;
  model?: string;
  placeholder: string;
  onSelect: (providerId: string, model: string) => void;
  onClear: () => void;
}) {
  const selection = providerId && model ? { providerId, model } : null;

  return (
    <div>
      <label className="text-xs font-medium text-muted-foreground mb-1.5 block">{label}</label>
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <ModelPickerPopover
            currentSelection={selection}
            onSelect={onSelect}
            trigger={
              <button
                type="button"
                className={cn(
                  'flex h-9 w-full items-center justify-between rounded-lg border px-3 py-2 text-sm transition-colors',
                  selection
                    ? 'border-primary/20 bg-primary/5'
                    : 'border-input bg-secondary/50 text-muted-foreground hover:bg-secondary/80',
                )}
              >
                <div className="flex items-center gap-2 min-w-0">
                  {selection && <ProviderIcon providerId={selection.providerId} size={14} />}
                  <span className="truncate">{selection?.model ?? placeholder}</span>
                </div>
                <IconChevronDown className="h-4 w-4 opacity-50 shrink-0 ml-2" />
              </button>
            }
          />
        </div>
        {selection && (
          <button
            type="button"
            onClick={onClear}
            className="flex items-center justify-center w-9 h-9 rounded-lg border border-border bg-secondary/50 hover:bg-destructive/10 hover:border-destructive/30 transition-colors flex-shrink-0 text-muted-foreground hover:text-destructive"
          >
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  );
}

export { MoaOverlaySection } from './AgentCapabilitiesMoaOverlaySection';
export { SessionPolicySection } from './AgentCapabilitiesSessionSection';
export { DeliveryAssuranceSection } from './AgentCapabilitiesDeliverySection';

const BUSY_INPUT_OPTIONS: { value: 'redirect' | 'steer' | 'queue'; labelKey: string }[] = [
  { value: 'redirect', labelKey: 'agent.busyInputRedirect' },
  { value: 'steer', labelKey: 'agent.busyInputSteer' },
  { value: 'queue', labelKey: 'agent.busyInputQueue' },
];

export function BusyInputModeSection({ editor, t }: SectionProps) {
  return (
    <div className="rounded-xl bg-card/60 border border-border/50 p-4">
      <div className="mb-3">
        <h4 className="text-sm font-medium text-foreground">{t('agent.busyInputMode')}</h4>
        <p className="text-xs text-muted-foreground mt-0.5">{t('agent.busyInputModeDesc')}</p>
      </div>
      <div className="flex gap-2">
        {BUSY_INPUT_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => editor.setBusyInputMode(opt.value)}
            className={cn(
              'flex-1 rounded-lg px-3 py-2 text-xs font-medium transition-colors border',
              editor.busyInputMode === opt.value
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border/50 bg-secondary/30 text-muted-foreground hover:bg-secondary/60',
            )}
          >
            {t(opt.labelKey)}
          </button>
        ))}
      </div>
    </div>
  );
}
