'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { PresetAgent } from '@/types/presetAgent';
import { AgentConfig } from '@/store/chat/types';
import { toast } from '@/hooks/useToast';
import useChatStore from '@/store/useChatStore';
import useAgentStore from '@/store/useAgentStore';

interface UsePresetAgentOptions {
  setAgentConfig: (config: AgentConfig | null) => void;
  originalAgentConfigRef: React.MutableRefObject<{
    agentId: string;
    selectedSkillIds: string[];
    selectedMcpNames: string[];
    systemPrompt: string;
    autoRestoreDomains: string[];
  } | null>;
}

interface UsePresetAgentReturn {
  // 状态（只读）
  selectedPresetId: string | undefined;

  // 操作
  handleSelectPreset: (preset: PresetAgent, workingDirectory?: string) => void;
  clearPresetSelection: () => void;
}

const isCLIVisualAgent = (agent: PresetAgent) => {
  return agent.category === 'cli_visual' && agent.requiresWorkingDirectory === true;
};

/**
 * 预置智能体管理 Hook
 *
 * 封装了预置智能体的选择、配置应用等逻辑。
 * CLI 可视化智能体通过 Tauri Sidecar 直接管理。
 */
export function usePresetAgent({
  setAgentConfig,
  originalAgentConfigRef,
}: UsePresetAgentOptions): UsePresetAgentReturn {
  const tAgent = useTranslations('agent.configPanel');
  const locale = useLocale();

  // 状态
  const [selectedPresetId, setSelectedPresetId] = useState<string | undefined>(undefined);

  // 防止重复初始化的标志
  const hasInitializedRef = useRef(false);

  // 应用预置智能体配置的通用函数
  const applyPresetAgentConfig = useCallback(
    async (preset: PresetAgent, workingDirectory?: string) => {
      let fullSystemPrompt = preset.systemPrompt || '';
      let fullSkillIds = preset.skillIds || [];

      try {
        const fullAgent = await useAgentStore.getState().fetchAgent(preset.id);
        if (fullAgent) {
          fullSystemPrompt = fullAgent.system_prompt || fullSystemPrompt;
          fullSkillIds = fullAgent.skill_ids || fullSkillIds;
        }
      } catch (e) {
        console.error('Failed to fetch full agent details for preset', e);
      }

      const config: AgentConfig = {
        agentId: preset.id,
        selectedSkillIds: fullSkillIds,
        skillConfigs: {},
        selectedMcpNames: [],
        systemPrompt: fullSystemPrompt,
        useGlobalInstruction: true,
        autoRestoreDomains: [],
        presetId: preset.id,
        presetName: preset.name,
        presetIcon: preset.icon,
      };

      // 如果有工作目录，存储在 agentDescription
      if (workingDirectory) {
        config.agentDescription = `workingDirectory:${workingDirectory}`;
      }

      setAgentConfig(config);
      originalAgentConfigRef.current = null;

      toast({
        title: tAgent('updateSuccess'),
        description: preset.name,
      });
    },
    [setAgentConfig, originalAgentConfigRef, tAgent],
  );

  // 默认选中通用助手（仅在首次加载且没有现有配置时执行）
  useEffect(() => {
    // 已初始化则跳过
    if (hasInitializedRef.current) return;
    hasInitializedRef.current = true;

    // 检查是否已有配置（从 store 读取当前状态）
    const currentAgentConfig = useChatStore.getState().agentConfig;

    // 如果已有配置且包含有效内容（MCP、技能、提示词等），保留现有配置
    const hasExistingConfig =
      currentAgentConfig &&
      ((currentAgentConfig.selectedMcpNames?.length ?? 0) > 0 ||
        (currentAgentConfig.selectedSkillIds?.length ?? 0) > 0 ||
        (currentAgentConfig.systemPrompt?.trim()?.length ?? 0) > 0 ||
        (currentAgentConfig.autoRestoreDomains?.length ?? 0) > 0 ||
        currentAgentConfig.agentId ||
        currentAgentConfig.presetId);

    if (hasExistingConfig) {
      // 保留现有配置，只同步 selectedPresetId 状态
      if (currentAgentConfig.presetId) {
        setSelectedPresetId(currentAgentConfig.presetId);
      }
      return;
    }

    // 没有现有配置，应用默认的通用助手
    useAgentStore
      .getState()
      .fetchAgents()
      .then(async () => {
        const agents = useAgentStore.getState().agents;
        const generalBp = agents.find((b) => b.id === 'builtin-general' || b.id === 'general');
        if (generalBp) {
          setSelectedPresetId(generalBp.id);

          let fullSystemPrompt = '';
          let fullSkillIds: string[] = [];
          try {
            const fullAgent = await useAgentStore.getState().fetchAgent(generalBp.id);
            if (fullAgent) {
              fullSystemPrompt = fullAgent.system_prompt || '';
              fullSkillIds = fullAgent.skill_ids || [];
            }
          } catch (e) {
            console.error('Failed to fetch full agent details for general', e);
          }

          const config: AgentConfig = {
            agentId: generalBp.id,
            selectedSkillIds: fullSkillIds,
            skillConfigs: {},
            selectedMcpNames: [],
            systemPrompt: fullSystemPrompt,
            useGlobalInstruction: true,
            autoRestoreDomains: [],
            presetId: generalBp.id,
            presetName: generalBp.name,
            presetIcon: generalBp.avatar_url?.replace('icon:', '') || 'MessageCircle',
          };
          setAgentConfig(config);
        }
      })
      .catch(console.error);
  }, [setAgentConfig, locale]);

  // 选择预置智能体
  // 对于 CLI 智能体，workingDirectory 由 PresetAgentGallery 组件传入
  const handleSelectPreset = useCallback(
    (preset: PresetAgent, workingDirectory?: string) => {
      // 如果点击的是当前已选中的预置智能体，则取消选中
      if (selectedPresetId === preset.id) {
        setSelectedPresetId(undefined);
        setAgentConfig(null);
        originalAgentConfigRef.current = null;
        return;
      }

      // 更新选中状态
      setSelectedPresetId(preset.id);

      // CLI 可视化智能体：应用配置，通过 Sidecar 管理
      if (isCLIVisualAgent(preset)) {
        applyPresetAgentConfig(preset, workingDirectory);
        return;
      }

      // 非 CLI 预置智能体：直接应用配置
      applyPresetAgentConfig(preset);
    },
    [selectedPresetId, setAgentConfig, originalAgentConfigRef, applyPresetAgentConfig],
  );

  // 清除预置智能体选中状态
  const clearPresetSelection = useCallback(() => {
    setSelectedPresetId(undefined);
  }, []);

  return {
    // 状态（只读）
    selectedPresetId,

    // 操作
    handleSelectPreset,
    clearPresetSelection,
  };
}
