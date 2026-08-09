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
import { Search, X } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { useTranslations } from 'next-intl';
import useProviderStore from '@/store/useProviderStore';
import { useShallow } from 'zustand/react/shallow';
import ProviderIcon from '@/components/features/settings/model-service/ProviderIcon';
import CapabilityIcons from '@/components/features/app-shell/capability-icons';
import { fetchModelCapabilitiesBatch, fetchModelSwitchPreflight, type ModelCapabilities, type ModelSwitchPreflightResult } from '@/services/llm-config';
import { getLiteLLMModelName } from '@/store/config/providerTypes';
import { formatTokens, formatPrice } from '@/lib/utils/modelFormatUtils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { useOrgModelPolicyStore } from '@/store/useOrgModelPolicyStore';
import { useOrgModelPolicySync } from '@/hooks/useOrgModelPolicySync';

interface PickerModelSelection {
  providerId: string;
  model: string;
}

type SlotMode = 'primary' | 'fallback' | 'safety';

interface MoaPresetOption {
  id: string;
  label: string;
  refCount: number;
}

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
  estimatedTokens,
  compressStartRatio,
  promptMode,
  turnCount,
  chatId,
  align = 'start',
  className,
}: ModelPickerPopoverProps) {
  const t = useTranslations('settings.defaultModel');
  const tCap = useTranslations('settings.modelCapabilities');
  const tMoa = useTranslations('settings.defaultModel.moaPreset');
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [activeSlot, setActiveSlot] = useState<SlotMode>('primary');
  const inputRef = useRef<HTMLInputElement>(null);
  const [capabilities, setCapabilities] = useState<Record<string, ModelCapabilities>>({});
  const [costPerMillion, setCostPerMillion] = useState<Record<string, { input: number; output: number }>>({});
  // 压缩预检结果：key = providerId/model
  const [preflightMap, setPreflightMap] = useState<Record<string, ModelSwitchPreflightResult>>({});
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
      tMoa('groupTitle').toLowerCase().includes(q) ||
      q.includes('moa') ||
      q.includes('mixture') ||
      q.includes('agent');
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

  const enabledModels = useMemo(() => getEnabledModels(), [getEnabledModels, providers]);

  useEffect(() => {
    if (open) {
      void loadPolicy();
    }
  }, [open, loadPolicy]);

  useEffect(() => {
    if (!open) return;
    setSearch('');
    setActiveSlot('primary');
    setTimeout(() => inputRef.current?.focus(), 0);

    const mapped: Record<string, ModelCapabilities> = {};
    const costs: Record<string, { input: number; output: number }> = {};
    const toFetch: string[] = [];
    const nameMap: Record<string, string> = {};

    for (const em of enabledModels) {
      const localKey = `${em.providerId}/${em.model}`;
      const local = customModelInfo[localKey];
      if (local) {
        mapped[em.model] = {
          supports_vision: local.supports_vision || false,
          supports_function_calling: local.supports_function_calling || false,
          supports_reasoning: local.supports_reasoning || false,
          supports_audio_input: local.supports_audio_input || false,
          supports_video_input: local.supports_video_input || false,
          supports_web_search: false,
          supports_prompt_caching: false,
          input_cost_per_token: local.input_cost_per_million || null,
          output_cost_per_token: local.output_cost_per_million || null,
          max_tokens: null,
          max_input_tokens: local.max_input_tokens || null,
          max_output_tokens: null,
        };
        if (local.input_cost_per_million != null && local.output_cost_per_million != null) {
          costs[em.model] = { input: local.input_cost_per_million, output: local.output_cost_per_million };
        }
      } else {
        const prov = providers.find((p) => p.id === em.providerId);
        const liteName = getLiteLLMModelName(em.providerId, em.model, prov?.providerType);
        toFetch.push(liteName);
        nameMap[liteName] = em.model;
      }
    }

    if (toFetch.length > 0) {
      fetchModelCapabilitiesBatch(toFetch).then((caps) => {
        for (const ln of toFetch) {
          if (caps[ln]) {
            const modelName = nameMap[ln];
            mapped[modelName] = caps[ln];
            const c = caps[ln];
            if (c.input_cost_per_token != null && c.output_cost_per_token != null) {
              costs[modelName] = {
                input: c.input_cost_per_token * 1_000_000,
                output: c.output_cost_per_token * 1_000_000,
              };
            }
          }
        }
        setCapabilities({ ...mapped });
        setCostPerMillion({ ...costs });
      });
    } else {
      setCapabilities(mapped);
      setCostPerMillion(costs);
    }
  }, [open, enabledModels, providers, customModelInfo]);

  const preflightRequestedRef = useRef<string>('');

  useEffect(() => {
    if (!open || !estimatedTokens || estimatedTokens <= 0 || Object.keys(capabilities).length === 0) {
      return;
    }
    const pairs: { providerId: string; model: string; liteName: string; maxInput: number | null }[] = [];
    for (const em of enabledModels) {
      const prov = providers.find((p) => p.id === em.providerId);
      if (!prov) continue;
      const caps = capabilities[em.model];
      if (!caps) continue;
      pairs.push({
        providerId: em.providerId,
        model: em.model,
        liteName: getLiteLLMModelName(em.providerId, em.model, prov.providerType),
        maxInput: caps.max_input_tokens ?? null,
      });
    }
    if (pairs.length === 0) return;

    const signature = `${chatId ?? ''}:${estimatedTokens}:${compressStartRatio ?? ''}:${promptMode ?? ''}:${turnCount ?? ''}:${pairs
      .map((p) => `${p.liteName}:${p.maxInput}`)
      .join('|')}`;
    if (preflightRequestedRef.current === signature) return;
    preflightRequestedRef.current = signature;

    fetchModelSwitchPreflight(
      estimatedTokens,
      pairs.map((p) => ({ model: p.liteName, max_input_tokens: p.maxInput })),
      compressStartRatio,
      promptMode,
      turnCount,
      chatId,
    ).then((results) => {
      const mapped: Record<string, ModelSwitchPreflightResult> = {};
      for (const p of pairs) {
        const result = results[p.liteName];
        if (result) mapped[`${p.providerId}/${p.model}`] = result;
      }
      setPreflightMap(mapped);
    });
  }, [open, estimatedTokens, capabilities, enabledModels, providers, compressStartRatio, promptMode, turnCount, chatId]);

  const grouped = useMemo(() => {
    const q = search.toLowerCase().trim();
    const result: { provider: (typeof providers)[0]; models: string[] }[] = [];
    const map: Record<string, (typeof result)[0]> = {};

    for (const em of enabledModels) {
      if (q && !em.model.toLowerCase().includes(q) && !em.providerName.toLowerCase().includes(q)) continue;
      if (!map[em.providerId]) {
        const prov = providers.find((p) => p.id === em.providerId);
        if (!prov) continue;
        map[em.providerId] = { provider: prov, models: [] };
        result.push(map[em.providerId]);
      }
      map[em.providerId].models.push(em.model);
    }
    return result;
  }, [enabledModels, providers, search]);

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
          <div className="px-2 pt-2 pb-1 border-b border-border">
            <div className="flex gap-1 p-0.5 rounded-lg bg-muted/60">
              <div
                onClick={() => setActiveSlot('primary')}
                className={cn(
                  'flex-1 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer select-none',
                  activeSlot === 'primary'
                    ? 'bg-background text-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <span className="flex items-center justify-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                  {t('primaryModel')}
                  {currentSelection && (
                    <span className="text-[10px] text-muted-foreground truncate max-w-[80px]">
                      {currentSelection.model}
                    </span>
                  )}
                </span>
              </div>
              <div
                onClick={() => setActiveSlot('fallback')}
                className={cn(
                  'flex-1 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer select-none',
                  activeSlot === 'fallback'
                    ? 'bg-background text-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <span className="flex items-center justify-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-sky-500" />
                  {t('fallbackSlot')}
                  {fallbackSelection ? (
                    <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground truncate max-w-[80px]">
                      {fallbackSelection.model}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onClearFallback?.();
                        }}
                        className="p-0 hover:text-destructive transition-colors"
                      >
                        <X size={8} />
                      </button>
                    </span>
                  ) : (
                    <span className="text-[10px] text-muted-foreground/50">{t('notSet')}</span>
                  )}
                </span>
              </div>
              {hasSafetyFallbackSupport && (
                <div
                  onClick={() => setActiveSlot('safety')}
                  className={cn(
                    'flex-1 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer select-none',
                    activeSlot === 'safety'
                      ? 'bg-background text-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  <span className="flex items-center justify-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    Safety
                    {safetyFallbackSelection ? (
                      <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground truncate max-w-[80px]">
                        {safetyFallbackSelection.model}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onClearSafetyFallback?.();
                          }}
                          className="p-0 hover:text-destructive transition-colors"
                        >
                          <X size={8} />
                        </button>
                      </span>
                    ) : (
                      <span className="text-[10px] text-muted-foreground/50">{t('notSet')}</span>
                    )}
                  </span>
                </div>
              )}
            </div>
          </div>
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
            {hasMoaPresets && activeSlot === 'primary' && visibleMoaPresets.length > 0 && (
              <div>
                <div className="flex items-center gap-2 px-3 py-2 text-xs font-semibold text-muted-foreground bg-primary/10 sticky top-0 border-b border-border/50">
                  <span className="inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border border-primary/40">
                    <span className="h-1 w-1 rounded-full bg-primary" />
                  </span>
                  <span>{tMoa('groupTitle')}</span>
                  <span className="ml-auto text-muted-foreground/60">{visibleMoaPresets.length}</span>
                </div>
                {visibleMoaPresets.map((preset) => {
                  const isActive = activeMoaPresetId === preset.id;
                  return (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => handleMoaPresetClick(preset.id)}
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
            )}
            {grouped.length === 0 && visibleMoaPresets.length === 0 ? (
              <div className="p-4 text-center text-sm text-muted-foreground">
                {enabledModels.length === 0 ? t('noEnabledModels') : t('noMatchingModels')}
              </div>
            ) : (
              grouped.map(({ provider, models }) => (
                <div key={provider.id}>
                  <div className="flex items-center gap-2 px-3 py-2 text-xs font-semibold text-muted-foreground bg-secondary/50 sticky top-0 border-b border-border/50">
                    <ProviderIcon providerId={provider.id} size={14} />
                    <span>{provider.name}</span>
                    <span className="ml-auto text-muted-foreground/60">{models.length}</span>
                  </div>
                  {models.map((model) => {
                    const isActive = activeSelection?.providerId === provider.id && activeSelection?.model === model;
                    const caps = capabilities[model];
                    const cost = costPerMillion[model];
                    const contextLabel = caps?.max_input_tokens ? formatTokens(caps.max_input_tokens) : null;
                    const preflightKey = `${provider.id}/${model}`;
                    const preflight = preflightMap[preflightKey];
                    const acknowledged = acknowledgedCountRef.current[preflightKey] ?? 0;
                    const showCompressWarning = !!preflight?.will_compress && acknowledged < 2;
                    const policyBlocked = restricted && !isModelAllowed(getLiteLLMModelName(provider.id, model, provider.providerType));
                    const liteModelName = getLiteLLMModelName(provider.id, model, provider.providerType);
                    const highlightColor =
                      activeSlot === 'primary'
                        ? 'bg-primary/10 text-primary font-medium'
                        : activeSlot === 'fallback'
                          ? 'bg-sky-50 dark:bg-sky-950/30 text-sky-600 dark:text-sky-300 font-medium'
                          : 'bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-300 font-medium';

                    return (
                      <button
                        key={model}
                        type="button"
                        data-testid={`model-item-${provider.id}-${model}`}
                        data-model-name={liteModelName}
                        disabled={policyBlocked}
                        aria-disabled={policyBlocked ? 'true' : undefined}
                        onClick={() => !policyBlocked && handleModelClick(provider.id, model)}
                        title={policyBlocked ? t('orgPolicyRestricted') : undefined}
                        className={cn(
                          'flex items-center w-full pl-9 pr-3 py-2.5 text-sm transition-colors gap-2',
                          policyBlocked
                            ? 'opacity-40 cursor-not-allowed'
                            : 'hover:bg-accent cursor-pointer',
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
                                {tCap('contextWindow')}: {caps!.max_input_tokens!.toLocaleString()} tokens
                              </TooltipContent>
                            </Tooltip>
                          )}
                          {showCompressWarning && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span
                                  data-testid={`preflight-warning-${provider.id}-${model}`}
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
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                                  {formatPrice(cost.input)}
                                </span>
                              </TooltipTrigger>
                              <TooltipContent side="top" className="text-xs">
                                {tCap('refCost')}: ↓{formatPrice(cost.input)} ↑{formatPrice(cost.output)}
                              </TooltipContent>
                            </Tooltip>
                          )}
                          {caps && <CapabilityIcons capabilities={caps} />}
                        </div>
                      </button>
                    );
                  })}
                </div>
              ))
            )}
          </div>
        </TooltipProvider>
      </PopoverContent>
    </Popover>
  );
}
