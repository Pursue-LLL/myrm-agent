'use client';

/**
 * [INPUT]
 * @/store/useProviderStore (POS: Provider 与启用模型状态)
 * @/store/useOrgModelPolicyStore (POS: 组织模型策略门禁)
 * @/services/llm-config::fetchModelCapabilitiesBatch (POS: 模型能力批量探测)
 *
 * [OUTPUT]
 * ModelPickerPopover: Provider 分组 + 可选 MoA preset 虚拟分组 + Primary/Fallback/Safety 槽位选择
 *
 * [POS]
 * 跨页面复用的模型选择 Popover（聊天输入、Settings、Cron 等）。
 */

import { useState, useMemo, useEffect, useRef, type ReactNode } from 'react';
import { Search } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { useTranslations } from 'next-intl';
import useProviderStore from '@/store/useProviderStore';
import { useShallow } from 'zustand/react/shallow';
import OpenCodeContributorNotice from '@/components/features/settings/model-service/OpenCodeContributorNotice';
import { anySelectionNeedsContributorNotice } from '@/components/features/settings/model-service/opencode-contributor-utils';
import { fetchModelCapabilitiesBatch, type ModelCapabilities } from '@/services/llm-config';
import { TooltipProvider } from '@/components/primitives/tooltip';
import { useOrgModelPolicyStore } from '@/store/useOrgModelPolicyStore';
import { useOrgModelPolicySync } from '@/hooks/useOrgModelPolicySync';
import {
  applyLocalOwnedFallbacks,
  collectLocalCapabilities,
  groupModelsByProvider,
  mergeFetchedCapabilities,
  type ModelCost,
  type MoaPresetOption,
  type PickerModelSelection,
  type SlotMode,
} from './model-picker-catalog';
import { ModelSlotTabs } from './model-picker-slot-tabs';
import { MoaPresetGroup, ProviderModelGroup, SmartRoutingOption } from './model-picker-options';
import { useModelSwitchPreflight } from './useModelSwitchPreflight';

interface ModelPickerPopoverProps {
  trigger: ReactNode;
  currentSelection?: PickerModelSelection | null;
  onSelect: (providerId: string, model: string) => void;
  fallbackSelection?: PickerModelSelection | null;
  onSelectFallback?: (providerId: string, model: string) => void;
  onClearFallback?: () => void;
  safetyFallbackSelection?: PickerModelSelection | null;
  onSelectSafetyFallback?: (providerId: string, model: string) => void;
  onClearSafetyFallback?: () => void;
  moaPresets?: MoaPresetOption[];
  activeMoaPresetId?: string | null;
  onSelectMoaPreset?: (presetId: string | null) => void;
  /** 是否可用智能路由虚拟选项 */
  isSmartRoutingAvailable?: boolean;
  /** 当前是否激活智能路由 */
  isSmartRoutingActive?: boolean;
  /** 选中智能路由回调 */
  onSelectSmartRouting?: () => void;
  /** 当前会话估算 tokens（聊天场景传入）；无值/<=0 时禁用压缩预检 */
  estimatedTokens?: number | null;
  /** agent 显式压缩起始比例（engineParams），缺省由 server 按目标模型 tier 推断 */
  compressStartRatio?: number | null;
  /** agent prompt 模式（full/lean/naked/search）；非 full 时 server 回退默认压缩比例 */
  promptMode?: string | null;
  /** 当前会话 human 消息数（轮数）；提供时 server 按运行时动态阈值判定压缩 */
  turnCount?: number | null;
  /** 当前会话 ID（聊天场景传入）；提供时 server 消费压缩无效 streak，避免误报 */
  chatId?: string | null;
  align?: 'start' | 'center' | 'end';
  className?: string;
}

export default function ModelPickerPopover({
  trigger,
  currentSelection,
  onSelect,
  fallbackSelection,
  onSelectFallback,
  onClearFallback,
  safetyFallbackSelection,
  onSelectSafetyFallback,
  onClearSafetyFallback,
  moaPresets,
  activeMoaPresetId,
  onSelectMoaPreset,
  isSmartRoutingAvailable = false,
  isSmartRoutingActive = false,
  onSelectSmartRouting,
  estimatedTokens,
  compressStartRatio,
  promptMode,
  turnCount,
  chatId,
  align = 'start',
  className,
}: ModelPickerPopoverProps) {
  const t = useTranslations('settings.defaultModel');
  const tMoa = useTranslations('settings.defaultModel.moaPreset');
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [activeSlot, setActiveSlot] = useState<SlotMode>('primary');
  const inputRef = useRef<HTMLInputElement>(null);
  const [capabilities, setCapabilities] = useState<Record<string, ModelCapabilities>>({});
  const [costPerMillion, setCostPerMillion] = useState<Record<string, ModelCost>>({});
  // 防骚扰：对同一目标模型已确认选择过的次数（>=2 后不再提示）
  const acknowledgedCountRef = useRef<Record<string, number>>({});
  const hasFallbackSupport = !!onSelectFallback;
  const hasSafetyFallbackSupport = !!onSelectSafetyFallback;
  const hasMoaPresets = !!onSelectMoaPreset && (moaPresets?.length ?? 0) > 0;

  const visibleMoaPresets = useMemo(() => {
    if (!hasMoaPresets || !moaPresets) {
      return [];
    }
    const q = search.toLowerCase().trim();
    if (!q) {
      return moaPresets;
    }
    const groupMatch =
      tMoa('groupTitle').toLowerCase().includes(q) || q.includes('moa') || q.includes('mixture') || q.includes('agent');
    return moaPresets.filter(
      (preset) => groupMatch || preset.label.toLowerCase().includes(q) || preset.id.toLowerCase().includes(q),
    );
  }, [hasMoaPresets, moaPresets, search, tMoa]);

  const { providers, getEnabledModels, customModelInfo } = useProviderStore(
    useShallow((s) => ({
      providers: s.providers,
      getEnabledModels: s.getEnabledModels,
      customModelInfo: s.customModelInfo,
    })),
  );

  const { restricted, loadPolicy, isModelAllowed } = useOrgModelPolicyStore();
  useOrgModelPolicySync();

  // `getEnabledModels` is a stable store action, so `providers` must drive recomputation when config loads after mount.
  // oxlint-disable-next-line react-hooks/exhaustive-deps -- providers is the data source read through the stable action
  const enabledModels = useMemo(() => getEnabledModels(), [getEnabledModels, providers]);

  useEffect(() => {
    if (open) {
      void loadPolicy();
    }
  }, [open, loadPolicy]);

  useEffect(() => {
    if (!open) {
      return;
    }
    setSearch('');
    setActiveSlot('primary');
    setTimeout(() => inputRef.current?.focus(), 0);

    const { mapped, costs, toFetch, nameMap } = collectLocalCapabilities(enabledModels, providers, customModelInfo);

    if (toFetch.length > 0) {
      fetchModelCapabilitiesBatch(toFetch).then((caps) => {
        mergeFetchedCapabilities(caps, toFetch, nameMap, mapped, costs);
        applyLocalOwnedFallbacks(costs, enabledModels, providers);
        setCapabilities({ ...mapped });
        setCostPerMillion({ ...costs });
      });
    } else {
      applyLocalOwnedFallbacks(costs, enabledModels, providers);
      setCapabilities(mapped);
      setCostPerMillion(costs);
    }
  }, [open, enabledModels, providers, customModelInfo]);

  const preflightMap = useModelSwitchPreflight({
    open,
    enabledModels,
    providers,
    capabilities,
    estimatedTokens,
    compressStartRatio,
    promptMode,
    turnCount,
    chatId,
  });

  const grouped = useMemo(
    () => groupModelsByProvider(enabledModels, providers, search, costPerMillion),
    [enabledModels, providers, search, costPerMillion],
  );

  const activeSelection =
    activeSlot === 'primary'
      ? currentSelection
      : activeSlot === 'fallback'
        ? fallbackSelection
        : safetyFallbackSelection;

  const handleModelClick = (providerId: string, model: string) => {
    const preflight = preflightMap[`${providerId}/${model}`];
    if (preflight?.will_compress) {
      const key = `${providerId}/${model}`;
      acknowledgedCountRef.current[key] = (acknowledgedCountRef.current[key] ?? 0) + 1;
    }
    if (activeSlot === 'fallback') {
      onSelectFallback?.(providerId, model);
    } else if (activeSlot === 'safety') {
      onSelectSafetyFallback?.(providerId, model);
    } else {
      onSelect(providerId, model);
      setOpen(false);
    }
  };

  const handleMoaPresetClick = (presetId: string) => {
    const nextId = activeMoaPresetId === presetId ? null : presetId;
    onSelectMoaPreset?.(nextId);
    setOpen(false);
  };

  const showContributorNotice = anySelectionNeedsContributorNotice([
    currentSelection,
    fallbackSelection,
    safetyFallbackSelection,
  ]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>{trigger}</PopoverTrigger>
      <PopoverContent
        data-testid="model-picker-popover"
        className={cn('w-96 max-w-[calc(100vw-2rem)] p-0', className)}
        align={align}
      >
        {/* Segmented tab for primary/fallback slot selection */}
        {hasFallbackSupport && (
          <ModelSlotTabs
            activeSlot={activeSlot}
            onSlotChange={setActiveSlot}
            currentSelection={currentSelection}
            fallbackSelection={fallbackSelection}
            onClearFallback={onClearFallback}
            hasSafetyFallbackSupport={hasSafetyFallbackSupport}
            safetyFallbackSelection={safetyFallbackSelection}
            onClearSafetyFallback={onClearSafetyFallback}
          />
        )}

        <div className="p-2 border-b border-border">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('searchModels')}
              className="w-full pl-8 pr-3 py-2 text-sm bg-secondary/50 border-none rounded-lg focus:outline-none"
            />
          </div>
        </div>
        <TooltipProvider>
          <div className="max-h-80 overflow-y-auto">
            {isSmartRoutingAvailable &&
              activeSlot === 'primary' &&
              (!search ||
                t('smartRouting.title').toLowerCase().includes(search.toLowerCase()) ||
                'auto smart routing 智能路由 自适应'.includes(search.toLowerCase())) && (
                <SmartRoutingOption
                  active={isSmartRoutingActive}
                  onSelect={() => {
                    onSelectSmartRouting?.();
                    setOpen(false);
                  }}
                />
              )}
            {hasMoaPresets && activeSlot === 'primary' && visibleMoaPresets.length > 0 && (
              <MoaPresetGroup
                presets={visibleMoaPresets}
                activePresetId={activeMoaPresetId}
                onSelectPreset={handleMoaPresetClick}
              />
            )}
            {grouped.length === 0 && visibleMoaPresets.length === 0 ? (
              <div className="p-4 text-center text-sm text-muted-foreground">
                {enabledModels.length === 0 ? t('noEnabledModels') : t('noMatchingModels')}
              </div>
            ) : (
              grouped.map(({ provider, models }) => (
                <ProviderModelGroup
                  key={provider.id}
                  provider={provider}
                  models={models}
                  activeSlot={activeSlot}
                  activeSelection={activeSelection}
                  capabilities={capabilities}
                  costPerMillion={costPerMillion}
                  preflightMap={preflightMap}
                  acknowledgedCounts={acknowledgedCountRef}
                  restricted={restricted}
                  isModelAllowed={isModelAllowed}
                  onModelClick={handleModelClick}
                />
              ))
            )}
          </div>
        </TooltipProvider>
        {showContributorNotice && (
          <div className="border-t border-border p-3">
            <OpenCodeContributorNotice variant="model" />
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
