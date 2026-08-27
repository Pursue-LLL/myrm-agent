'use client';

/**
 * [INPUT]
 * @/store/useChatStore (POS: 会话 agentConfig / activeMoaPresetId)
 * @/store/useProviderStore (POS: 默认与 per-agent 模型绑定)
 * @/lib/model-binding (POS: 活动模型与 picker 触发器展示)
 * @/lib/moaPresetUtils (POS: MoA preset 配置检测)
 *
 * [OUTPUT]
 * BaseModelSelector: 聊天输入区模型选择触发器 + ModelPickerPopover 接线
 *
 * [POS]
 * MessageInput 主模型快速切换；Agent 模式下可选 MoA preset 虚拟分组。
 */

import { useMemo, useCallback, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';
import { useTranslations } from 'next-intl';
import useProviderStore from '@/store/useProviderStore';
import useChatStore from '@/store/useChatStore';
import { useShallow } from 'zustand/react/shallow';
import {
  resolveActiveModelSelection,
  resolveActiveFallbackSelection,
  resolveModelPickerTriggerDisplay,
  isSmartRoutingConfigured,
} from '@/lib/model-binding';
import {
  listMoaPresetOptions,
  isMoaPresetConfigured,
  resolveMoaPresetLabelKey,
  isActiveMoaPresetAvailable,
} from '@/lib/moaPresetUtils';
import ModelPickerPopover from '@/components/features/app-shell/model-picker-popover';
import ProviderIcon from '@/components/features/settings/model-service/ProviderIcon';

type SingleModelSelection = { providerId: string; model: string };

const BaseModelSelector = () => {
  const commonT = useTranslations('common');
  const moaPresetT = useTranslations('settings.defaultModel.moaPreset');
  const defaultModelT = useTranslations('settings.defaultModel');

  const { agentConfig, actionMode, activeMoaPresetId, updateAgentConfig, setActiveMoaPresetId } = useChatStore(
    useShallow((state) => ({
      agentConfig: state.agentConfig,
      actionMode: state.actionMode,
      activeMoaPresetId: state.activeMoaPresetId,
      updateAgentConfig: state.updateAgentConfig,
      setActiveMoaPresetId: state.setActiveMoaPresetId,
    })),
  );

  const messages = useChatStore(useShallow((state) => state.messages));
  const chatId = useChatStore((state) => state.chatId);

  const {
    providers,
    defaultModelConfig,
    getEnabledModels,
    setBaseModel,
    setBaseModelFallback,
    setFastModeModel,
    isInitialized,
    initProviders,
  } = useProviderStore(
    useShallow((state) => ({
      providers: state.providers,
      defaultModelConfig: state.defaultModelConfig,
      getEnabledModels: state.getEnabledModels,
      setBaseModel: state.setBaseModel,
      setBaseModelFallback: state.setBaseModelFallback,
      setFastModeModel: state.setFastModeModel,
      isInitialized: state.isInitialized,
      initProviders: state.initProviders,
    })),
  );

  useEffect(() => {
    if (!isInitialized) {
      void initProviders();
    }
  }, [isInitialized, initProviders]);

  const moaPresetAvailable = useMemo(
    () => isMoaPresetConfigured(agentConfig?.engineParams),
    [agentConfig?.engineParams],
  );

  useEffect(() => {
    if (!moaPresetAvailable && activeMoaPresetId) {
      setActiveMoaPresetId(null);
    }
  }, [moaPresetAvailable, activeMoaPresetId, setActiveMoaPresetId]);

  const showMoaPresets = actionMode === 'agent' && moaPresetAvailable;

  const moaPresets = useMemo(() => {
    if (!showMoaPresets) {
      return [];
    }
    return listMoaPresetOptions(agentConfig?.engineParams).map((preset) => ({
      id: preset.id,
      label: moaPresetT(preset.labelKey),
      refCount: preset.refCount,
    }));
  }, [showMoaPresets, agentConfig?.engineParams, moaPresetT]);

  useEffect(() => {
    if (!showMoaPresets || !activeMoaPresetId) {
      return;
    }
    if (!isActiveMoaPresetAvailable(agentConfig?.engineParams, activeMoaPresetId)) {
      setActiveMoaPresetId(null);
    }
  }, [showMoaPresets, activeMoaPresetId, agentConfig?.engineParams, setActiveMoaPresetId]);

  const enabledModels = useMemo(() => getEnabledModels(), [getEnabledModels, providers]);

  const currentSelection = useMemo(
    () => resolveActiveModelSelection(actionMode, agentConfig, defaultModelConfig, providers),
    [actionMode, agentConfig, defaultModelConfig, providers],
  );

  const fallbackSelection = useMemo(
    () => resolveActiveFallbackSelection(actionMode, agentConfig, defaultModelConfig, providers),
    [actionMode, agentConfig, defaultModelConfig, providers],
  );

  const safetyFallbackSelection = useMemo(
    () =>
      actionMode === 'agent' && agentConfig?.safetyFallbackModelSelection
        ? agentConfig.safetyFallbackModelSelection
        : null,
    [actionMode, agentConfig],
  );

  const triggerDisplay = useMemo(
    () => resolveModelPickerTriggerDisplay(actionMode, agentConfig, defaultModelConfig, providers, activeMoaPresetId),
    [actionMode, agentConfig, defaultModelConfig, providers, activeMoaPresetId],
  );

  const isRoutingConfigured = useMemo(
    () => isSmartRoutingConfigured(agentConfig, defaultModelConfig),
    [agentConfig, defaultModelConfig],
  );

  const handleSelectSmartRouting = useCallback(() => {
    if (actionMode === 'agent') {
      updateAgentConfig({ modelSelection: null });
    }
  }, [actionMode, updateAgentConfig]);

  const currentModelName = useMemo(() => {
    if (triggerDisplay.isSmartRouting) {
      return defaultModelT('smartRouting.autoTitle');
    }
    if (!triggerDisplay.modelName) {
      return commonT('notConfigured');
    }
    return triggerDisplay.modelName;
  }, [triggerDisplay.isSmartRouting, triggerDisplay.modelName, defaultModelT, commonT]);

  // 当前会话估算 tokens 与轮数（取最近一条 assistant 消息的 provider 真实数据）
  // estimatedTokens 来自服务端 prompt_tokens；turnCount 优先用服务端全量 human 数，
  // 缺失时 fallback 本地消息统计（与运行时 compress_processor 口径一致）。
  const contextBudgetInfo = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i];
      if (msg.role === 'assistant' && msg.contextBudget) {
        const { current_tokens, messages_estimated_tokens, turn_count } = msg.contextBudget;
        return {
          estimatedTokens: current_tokens || messages_estimated_tokens || 0,
          serverTurnCount: typeof turn_count === 'number' ? turn_count : null,
        };
      }
    }
    return { estimatedTokens: 0, serverTurnCount: null };
  }, [messages]);

  const estimatedTokens = contextBudgetInfo.estimatedTokens;

  const turnCount = useMemo(() => {
    if (contextBudgetInfo.serverTurnCount !== null) {
      return contextBudgetInfo.serverTurnCount;
    }
    return messages.filter((m) => m.role === 'user').length;
  }, [contextBudgetInfo.serverTurnCount, messages]);

  const compressStartRatio = useMemo(() => {
    const value = agentConfig?.engineParams?.compress_start_ratio;
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
  }, [agentConfig?.engineParams]);

  const promptMode = useMemo(() => agentConfig?.promptMode ?? null, [agentConfig?.promptMode]);

  const moaChipLabel = useMemo(() => {
    const labelKey = resolveMoaPresetLabelKey(triggerDisplay.moaPresetId);
    if (!labelKey) {
      return null;
    }
    return moaPresetT('activeLabel', { preset: moaPresetT(labelKey) });
  }, [triggerDisplay.moaPresetId, moaPresetT]);

  const isCurrentSelectionValid = useMemo(() => {
    if (!currentSelection) {
      return false;
    }
    return enabledModels.some(
      (m) => m.providerId === currentSelection.providerId && m.model === currentSelection.model,
    );
  }, [currentSelection, enabledModels]);

  const handleModelSelect = useCallback(
    (providerId: string, model: string) => {
      const selection: SingleModelSelection = { providerId, model };

      if (actionMode === 'fast') {
        setFastModeModel(selection);
      } else if (actionMode === 'agent') {
        updateAgentConfig({ modelSelection: selection });
      } else {
        setBaseModel(selection);
      }
    },
    [actionMode, setFastModeModel, setBaseModel, updateAgentConfig],
  );

  const handleFallbackSelect = useCallback(
    (providerId: string, model: string) => {
      const selection: SingleModelSelection = { providerId, model };

      if (actionMode === 'agent') {
        updateAgentConfig({ fallbackModelSelection: selection });
      } else {
        setBaseModelFallback(selection);
      }
    },
    [actionMode, setBaseModelFallback, updateAgentConfig],
  );

  const handleClearFallback = useCallback(() => {
    if (actionMode === 'agent') {
      updateAgentConfig({ fallbackModelSelection: null });
    } else {
      setBaseModelFallback(null);
    }
  }, [actionMode, setBaseModelFallback, updateAgentConfig]);

  const handleSafetyFallbackSelect = useCallback(
    (providerId: string, model: string) => {
      const selection: SingleModelSelection = { providerId, model };
      if (actionMode === 'agent') {
        updateAgentConfig({ safetyFallbackModelSelection: selection });
      }
    },
    [actionMode, updateAgentConfig],
  );

  const handleClearSafetyFallback = useCallback(() => {
    if (actionMode === 'agent') {
      updateAgentConfig({ safetyFallbackModelSelection: null });
    }
  }, [actionMode, updateAgentConfig]);

  const isProviderDisabled = useMemo(() => {
    if (!currentSelection) {
      return false;
    }
    const provider = providers.find((p) => p.id === currentSelection.providerId);
    return provider ? !provider.isEnabled : true;
  }, [currentSelection, providers]);

  return (
    <div className="flex items-center gap-2">
      <ModelPickerPopover
        currentSelection={currentSelection}
        onSelect={handleModelSelect}
        fallbackSelection={fallbackSelection}
        onSelectFallback={handleFallbackSelect}
        onClearFallback={handleClearFallback}
        safetyFallbackSelection={safetyFallbackSelection}
        onSelectSafetyFallback={actionMode === 'agent' ? handleSafetyFallbackSelect : undefined}
        onClearSafetyFallback={actionMode === 'agent' ? handleClearSafetyFallback : undefined}
        moaPresets={moaPresets}
        activeMoaPresetId={activeMoaPresetId}
        onSelectMoaPreset={showMoaPresets ? setActiveMoaPresetId : undefined}
        isSmartRoutingAvailable={isRoutingConfigured}
        isSmartRoutingActive={triggerDisplay.isSmartRouting}
        onSelectSmartRouting={handleSelectSmartRouting}
        estimatedTokens={estimatedTokens}
        compressStartRatio={compressStartRatio}
        promptMode={promptMode}
        turnCount={turnCount}
        chatId={chatId}
        trigger={
          <button
            type="button"
            data-testid="model-picker-trigger"
            className="group relative isolate flex h-fit focus:outline-none"
          >
            <div className="absolute inset-0 bg-black/[0.04] dark:bg-white/[0.06] rounded-[10px] transition-colors duration-300" />
            <div className="relative z-10 flex h-8 min-h-8 items-center gap-1.5 px-2.5 py-0.5">
              {triggerDisplay.isSmartRouting ? (
                <span className="shrink-0 text-emerald-600 dark:text-emerald-400 font-bold text-xs">✨</span>
              ) : currentSelection && isCurrentSelectionValid ? (
                <ProviderIcon
                  providerId={currentSelection.providerId}
                  size={16}
                  className="shrink-0 opacity-60 group-hover:opacity-100 transition-opacity duration-300"
                />
              ) : (
                <ChevronDown
                  size={16}
                  className="shrink-0 text-black/40 dark:text-white/40 group-hover:text-black dark:group-hover:text-white transition-colors duration-300"
                />
              )}
              <span className="inline text-xs font-medium text-black/60 dark:text-white/60 group-hover:text-black dark:group-hover:text-white transition-colors duration-300 truncate max-w-[120px] sm:max-w-none">
                {currentModelName}
              </span>
              {triggerDisplay.isSmartRouting ? (
                <span className="shrink-0 rounded-md bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                  Auto
                </span>
              ) : moaChipLabel ? (
                <span className="shrink-0 rounded-md bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                  {moaChipLabel}
                </span>
              ) : null}
              <ChevronDown
                size={14}
                className="text-black/40 dark:text-white/40 group-hover:text-black dark:group-hover:text-white transition-colors duration-300"
              />
            </div>
          </button>
        }
      />
      {isProviderDisabled && (
        <span className="flex items-center text-amber-500" title={commonT('providerDisabledWarning')}>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            <path d="M12 9v4" />
            <path d="M12 17h.01" />
          </svg>
        </span>
      )}
    </div>
  );
};

export default BaseModelSelector;
