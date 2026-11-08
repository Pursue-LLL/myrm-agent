'use client';

/**
 * [INPUT] @/store/config/providerTypes::getRoutedModelName (POS: 路由名), ./model-picker-catalog (POS: 选择器数据类型)
 * [OUTPUT] SmartRoutingOption: 智能路由虚拟选项; MoaPresetGroup: MoA preset 虚拟分组; ProviderModelGroup: Provider 分组及其模型行（上下文窗口 / 压缩预警 / 成本 / 能力徽标，组织策略灰显）
 * [POS] ModelPickerPopover 的列表区块，纯展示，选择与槽位状态由父组件持有。
 */

import type { RefObject } from 'react';
import { useTranslations } from 'next-intl';
import type { ModelCost, MoaPresetOption, PickerModelSelection, SlotMode } from './model-picker-catalog';
import { ArrowsSplit } from '@phosphor-icons/react';
import { cn } from '@/lib/utils/classnameUtils';
import ProviderIcon from '@/components/features/settings/model-service/ProviderIcon';
import CapabilityIcons from '@/components/features/app-shell/capability-icons';
import { type ModelCapabilities, type ModelSwitchPreflightResult } from '@/services/llm-config';
import { getRoutedModelName, type ProviderConfig } from '@/store/config/providerTypes';
import { formatTokens, formatPrice } from '@/lib/utils/modelFormatUtils';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';

export function SmartRoutingOption({ active, onSelect }: { active: boolean; onSelect: () => void }) {
  const t = useTranslations('settings.defaultModel');

  return (
    <div className="border-b border-border/50 bg-emerald-500/[0.03]">
      <button
        type="button"
        data-testid="smart-routing-option"
        onClick={onSelect}
        className={cn(
          'flex items-center w-full px-3 py-2.5 text-sm transition-colors gap-2.5 hover:bg-emerald-500/10 cursor-pointer',
          active && 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium',
        )}
      >
        <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 shadow-sm">
          <ArrowsSplit size={14} weight="bold" aria-hidden="true" />
        </span>
        <div className="flex flex-col text-left truncate flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="truncate font-medium text-foreground">{t('smartRouting.autoTitle')}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-medium shrink-0">
              {t('smartRouting.recommended')}
            </span>
          </div>
          <span className="text-[10px] text-muted-foreground truncate">{t('smartRouting.autoDescription')}</span>
        </div>
      </button>
    </div>
  );
}

interface MoaPresetGroupProps {
  presets: MoaPresetOption[];
  activePresetId: string | null | undefined;
  onSelectPreset: (presetId: string) => void;
}

export function MoaPresetGroup({ presets, activePresetId, onSelectPreset }: MoaPresetGroupProps) {
  const tMoa = useTranslations('settings.defaultModel.moaPreset');

  return (
    <div>
      <div className="flex items-center gap-2 px-3 py-2 text-xs font-semibold text-muted-foreground bg-primary/10 sticky top-0 border-b border-border/50">
        <span className="inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border border-primary/40">
          <span className="h-1 w-1 rounded-full bg-primary" />
        </span>
        <span>{tMoa('groupTitle')}</span>
        <span className="ml-auto text-muted-foreground/60">{presets.length}</span>
      </div>
      {presets.map((preset) => {
        const isActive = activePresetId === preset.id;
        return (
          <button
            key={preset.id}
            type="button"
            onClick={() => onSelectPreset(preset.id)}
            className={cn(
              'flex items-center w-full pl-9 pr-3 py-2.5 text-sm transition-colors gap-2 hover:bg-accent cursor-pointer',
              isActive && 'bg-primary/10 text-primary font-medium',
            )}
          >
            <span className="truncate flex-1 text-left">{preset.label}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground shrink-0">
              {tMoa('refCount', { count: preset.refCount })}
            </span>
          </button>
        );
      })}
    </div>
  );
}

interface ModelRowProps {
  providerId: string;
  model: string;
  liteModelName: string;
  isActive: boolean;
  highlightColor: string;
  caps: ModelCapabilities | undefined;
  cost: ModelCost | undefined;
  preflight: ModelSwitchPreflightResult | undefined;
  acknowledged: number;
  policyBlocked: boolean;
  onModelClick: (providerId: string, model: string) => void;
}

function ModelRow({
  providerId,
  model,
  liteModelName,
  isActive,
  highlightColor,
  caps,
  cost,
  preflight,
  acknowledged,
  policyBlocked,
  onModelClick,
}: ModelRowProps) {
  const t = useTranslations('settings.defaultModel');
  const tCap = useTranslations('settings.modelCapabilities');
  const contextLabel = caps?.max_input_tokens ? formatTokens(caps.max_input_tokens) : null;
  const showCompressWarning = !!preflight?.will_compress && acknowledged < 2;

  return (
    <button
      type="button"
      data-testid={`model-item-${providerId}-${model}`}
      data-model-name={liteModelName}
      disabled={policyBlocked}
      aria-disabled={policyBlocked ? 'true' : undefined}
      onClick={() => !policyBlocked && onModelClick(providerId, model)}
      title={policyBlocked ? t('orgPolicyRestricted') : undefined}
      className={cn(
        'flex items-center w-full pl-9 pr-3 py-2.5 text-sm transition-colors gap-2',
        policyBlocked ? 'opacity-40 cursor-not-allowed' : 'hover:bg-accent cursor-pointer',
        isActive && !policyBlocked && highlightColor,
      )}
    >
      <span className="truncate flex-1 text-left flex items-center gap-2">{model}</span>
      <div className="flex items-center gap-1 shrink-0">
        {contextLabel && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium">
                {contextLabel}
              </span>
            </TooltipTrigger>
            <TooltipContent side="top" className="text-xs">
              {tCap('contextWindow')}: {caps?.max_input_tokens?.toLocaleString()} tokens
            </TooltipContent>
          </Tooltip>
        )}
        {showCompressWarning && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                data-testid={`preflight-warning-${providerId}-${model}`}
                className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-600 dark:text-amber-400 font-medium"
              >
                {t('preflightCompress')}
              </span>
            </TooltipTrigger>
            <TooltipContent side="top" className="text-xs">
              {t('preflightCompressDetail', {
                threshold: (preflight.compress_threshold ?? 0).toLocaleString(),
              })}
            </TooltipContent>
          </Tooltip>
        )}
        {cost && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                className={cn(
                  'text-[10px] px-1.5 py-0.5 rounded font-medium',
                  cost.isLocalOwned
                    ? 'bg-emerald-500/10 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400 border border-emerald-500/20'
                    : 'bg-muted text-muted-foreground',
                )}
              >
                {formatPrice(cost.input)}
              </span>
            </TooltipTrigger>
            <TooltipContent side="top" className="text-xs">
              {cost.isLocalOwned
                ? tCap('localOwnedMarginalCostHint')
                : `${tCap('refCost')}: ↓${formatPrice(cost.input)} ↑${formatPrice(cost.output)}`}
            </TooltipContent>
          </Tooltip>
        )}
        {caps && <CapabilityIcons capabilities={caps} />}
      </div>
    </button>
  );
}

interface ProviderModelGroupProps {
  provider: ProviderConfig;
  models: string[];
  activeSlot: SlotMode;
  activeSelection: PickerModelSelection | null | undefined;
  capabilities: Record<string, ModelCapabilities>;
  costPerMillion: Record<string, ModelCost>;
  preflightMap: Record<string, ModelSwitchPreflightResult>;
  /** Per-target counts of confirmed compression warnings (anti-nagging); read at render time. */
  acknowledgedCounts: RefObject<Record<string, number>>;
  restricted: boolean;
  isModelAllowed: (modelName: string) => boolean;
  onModelClick: (providerId: string, model: string) => void;
}

export function ProviderModelGroup({
  provider,
  models,
  activeSlot,
  activeSelection,
  capabilities,
  costPerMillion,
  preflightMap,
  acknowledgedCounts,
  restricted,
  isModelAllowed,
  onModelClick,
}: ProviderModelGroupProps) {
  return (
    <div>
      <div className="flex items-center gap-2 px-3 py-2 text-xs font-semibold text-muted-foreground bg-secondary/50 sticky top-0 border-b border-border/50">
        <ProviderIcon providerId={provider.id} size={14} />
        <span>{provider.name}</span>
        <span className="ml-auto text-muted-foreground/60">{models.length}</span>
      </div>
      {models.map((model) => {
        const isActive = activeSelection?.providerId === provider.id && activeSelection?.model === model;
        const caps = capabilities[model];
        const cost = costPerMillion[model];
        const preflightKey = `${provider.id}/${model}`;
        const preflight = preflightMap[preflightKey];
        const acknowledged = acknowledgedCounts.current[preflightKey] ?? 0;
        const liteModelName = getRoutedModelName(provider.id, model, provider.providerType);
        const policyBlocked = restricted && !isModelAllowed(liteModelName);
        const highlightColor =
          activeSlot === 'primary'
            ? 'bg-primary/10 text-primary font-medium'
            : activeSlot === 'fallback'
              ? 'bg-sky-50 dark:bg-sky-950/30 text-sky-600 dark:text-sky-300 font-medium'
              : 'bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-300 font-medium';

        return (
          <ModelRow
            key={model}
            providerId={provider.id}
            model={model}
            liteModelName={liteModelName}
            isActive={isActive}
            highlightColor={highlightColor}
            caps={caps}
            cost={cost}
            preflight={preflight}
            acknowledged={acknowledged}
            policyBlocked={policyBlocked}
            onModelClick={onModelClick}
          />
        );
      })}
    </div>
  );
}
