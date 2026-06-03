/**
 * [INPUT]
 * - @/store/useChatStore (POS: 聊天状态总线)
 * - @/store/useProviderStore (POS: 模型与 Provider 注册表)
 * - @/lib/model-binding (POS: 模型选择解析)
 * - @/store/useFeatureGateStore (POS: 功能门控状态)
 * - ThinkingIntensityButton::useGlobalIntensity (POS: 响应式思考强度状态)
 *
 * [OUTPUT]
 * - useMobileSheetEntries: 为 MobileActionSheet 构建 entries 数据的 hook。
 *
 * [POS]
 * 移动端 ActionSheet 数据构建层。将分散在各独立组件中的功能入口聚合为统一的列表数据结构。
 */
'use client';

import { useMemo, useCallback } from 'react';
import { Brain, Sparkles, Target } from 'lucide-react';
import { useTranslations } from 'next-intl';
import useChatStore from '@/store/useChatStore';
import useProviderStore from '@/store/useProviderStore';
import { useShallow } from 'zustand/react/shallow';
import { resolveActiveModelSelection } from '@/lib/model-binding';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import {
  type IntensityLevel,
  setGlobalIntensity,
  useGlobalIntensity,
} from '@/components/features/message-input-actions/ThinkingIntensityButton';
import type { MobileActionSheetEntry, MobileActionSheetOption } from './MobileActionSheet';

const INTENSITY_LEVELS: IntensityLevel[] = ['off', 'low', 'medium', 'high', 'xhigh', 'max'];

interface UseMobileSheetEntriesOptions {
  onClose: () => void;
}

export function useMobileSheetEntries({ onClose }: UseMobileSheetEntriesOptions): MobileActionSheetEntry[] {
  const t = useTranslations('common');
  const thinkT = useTranslations('thinkingIntensity');

  const { agentConfig, actionMode, updateAgentConfig, isGoalMode, setIsGoalMode } = useChatStore(
    useShallow((s) => ({
      agentConfig: s.agentConfig,
      actionMode: s.actionMode,
      updateAgentConfig: s.updateAgentConfig,
      isGoalMode: s.isGoalMode,
      setIsGoalMode: s.setIsGoalMode,
    })),
  );

  const { providers, defaultModelConfig, getEnabledModels } = useProviderStore(
    useShallow((s) => ({
      providers: s.providers,
      defaultModelConfig: s.defaultModelConfig,
      getEnabledModels: s.getEnabledModels,
    })),
  );

  const isGoalsEnabled = useFeatureGateStore((s) => s.isEnabled('goals_system'));

  const currentSelection = useMemo(
    () => resolveActiveModelSelection(actionMode, agentConfig, defaultModelConfig, providers),
    [actionMode, agentConfig, defaultModelConfig, providers],
  );

  const enabledModels = useMemo(() => getEnabledModels(), [getEnabledModels, providers]);

  const handleModelSelect = useCallback(
    (key: string) => {
      const [providerId, model] = key.split('::');
      if (!providerId || !model || !agentConfig) return;
      updateAgentConfig({ modelSelection: { providerId, model } });
    },
    [agentConfig, updateAgentConfig],
  );

  const handleGoalToggle = useCallback(() => {
    setIsGoalMode(!isGoalMode);
    onClose();
  }, [isGoalMode, setIsGoalMode, onClose]);

  const currentModelLabel = currentSelection?.model ?? t('selectModel');

  const modelOptions: MobileActionSheetOption[] = useMemo(
    () =>
      enabledModels.map((m) => ({
        key: `${m.providerId}::${m.model}`,
        label: m.model,
        description: m.providerName,
        active: currentSelection?.providerId === m.providerId && currentSelection?.model === m.model,
      })),
    [enabledModels, currentSelection],
  );

  const { intensity: currentIntensity } = useGlobalIntensity();
  const currentEffort = currentIntensity === 'off' ? undefined : currentIntensity;

  const handleIntensitySelect = useCallback((key: string) => {
    setGlobalIntensity(key as IntensityLevel);
  }, []);

  const intensityOptions: MobileActionSheetOption[] = useMemo(
    () =>
      INTENSITY_LEVELS.map((level) => ({
        key: level,
        label: thinkT(level, { defaultMessage: level }),
        active: currentEffort === (level === 'off' ? undefined : level),
      })),
    [thinkT, currentEffort],
  );

  return useMemo(() => {
    const entries: MobileActionSheetEntry[] = [
      {
        key: 'model',
        icon: <Brain size={16} />,
        label: t('model', { defaultMessage: '模型' }),
        meta: currentModelLabel,
        submenu: {
          title: t('model', { defaultMessage: '模型' }),
          options: modelOptions,
          onSelect: handleModelSelect,
        },
      },
      {
        key: 'thinking',
        icon: <Sparkles size={16} />,
        label: thinkT('title', { defaultMessage: '思考强度' }),
        meta: currentEffort ?? thinkT('off', { defaultMessage: 'off' }),
        submenu: {
          title: thinkT('title', { defaultMessage: '思考强度' }),
          options: intensityOptions,
          onSelect: handleIntensitySelect,
        },
      },
    ];

    if (isGoalsEnabled) {
      entries.push({
        key: 'goal',
        icon: <Target size={16} />,
        label: t('goalMode', { defaultMessage: '目标模式' }),
        meta: isGoalMode ? t('enabled', { defaultMessage: '已开启' }) : undefined,
        onClick: handleGoalToggle,
      });
    }

    return entries;
  }, [
    t,
    thinkT,
    currentModelLabel,
    currentEffort,
    modelOptions,
    handleModelSelect,
    handleIntensitySelect,
    intensityOptions,
    isGoalsEnabled,
    isGoalMode,
    handleGoalToggle,
  ]);
}
