import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import useAgentStore from '@/store/useAgentStore';
import { useSkillStore } from '@/store/skill';
import useAuthStore from '@/store/useAuthStore';
import { createAgent, type AgentCreate } from '@/services/agent';
import { isRiskHeldError } from '@/services/riskHeldToast';
import { toast } from '@/hooks/shared/useToast';
import { useDefaultAgentBootstrap } from '@/hooks/agent/useDefaultAgentBootstrap';
import type { ConfigCardType } from '@/components/features/chat-window/agent-config-panel/AgentConfigCards';
import { createSaveConfigHandler } from './config-panel/handlers';

/**
 * AgentConfigPanel 业务逻辑 Hook
 *
 * 封装智能体配置面板的状态与动作：
 * - Store 集成（Chat、Config、Skill、Agent、Auth）与进入面板时的数据加载
 * - 编辑弹窗、打字机欢迎消息的本地状态
 * - 已启用技能 / MCP 与选中详情的派生数据
 * - 保存弹窗配置，以及把当前配置保存为新智能体（已保存的智能体在 Settings 的智能体页编辑）
 */
export const useAgentConfigPanel = () => {
  const router = useRouter();
  const t = useTranslations('agent.configPanel');
  const tAgent = useTranslations('agent');
  const tIndicator = useTranslations('agent.indicator');

  // ==================== Store Hooks ====================

  // Chat store
  const {
    agentConfig,
    setAgentConfig,
    updateAgentConfig,
    actionMode,
    isConfigPanelExpanded,
    currentBuiltinTools,
    setCurrentBuiltinTools,
  } = useChatStore(
    useShallow((state) => ({
      agentConfig: state.agentConfig,
      setAgentConfig: state.setAgentConfig,
      updateAgentConfig: state.updateAgentConfig,
      actionMode: state.actionMode,
      isConfigPanelExpanded: state.isConfigPanelExpanded,
      currentBuiltinTools: state.currentBuiltinTools,
      setCurrentBuiltinTools: state.setCurrentBuiltinTools,
    })),
  );

  // Config store - MCP
  const mcpConfigs = useConfigStore((state) => state.mcpConfigs);
  const enabledMcps = useMemo(() => mcpConfigs.filter((m) => m.enabled), [mcpConfigs]);

  // Skill store
  const {
    marketSkills,
    localSkills,
    isSkillEnabled,
    fetchMarketSkills,
    fetchUserSkillConfig,
    fetchLocalSkills,
    fetchLocalSkillPaths,
  } = useSkillStore(
    useShallow((state) => ({
      marketSkills: state.marketSkills,
      localSkills: state.localSkills,
      isSkillEnabled: state.isSkillEnabled,
      fetchMarketSkills: state.fetchMarketSkills,
      fetchUserSkillConfig: state.fetchUserSkillConfig,
      fetchLocalSkills: state.fetchLocalSkills,
      fetchLocalSkillPaths: state.fetchLocalSkillPaths,
    })),
  );

  // Agent store
  const fetchAgents = useAgentStore((state) => state.fetchAgents);

  // Auth store
  const user = useAuthStore((state) => state.user);

  // ==================== Local State ====================

  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editDialogType, setEditDialogType] = useState<ConfigCardType>('skills');
  const [isSavingAgent, setIsSavingAgent] = useState(false);

  // 打字机欢迎消息状态
  const [showTypewriter, setShowTypewriter] = useState(false);
  const prevActionModeRef = useRef<string | null>(null);

  // 首次进入且无任何配置时选中内置通用智能体
  useDefaultAgentBootstrap(setAgentConfig);

  // ==================== Memoized Values ====================

  // 获取已启用的技能详情（包括市场技能、个人技能和本地技能，排除 user_invocable=false）
  const enabledSkills = useMemo(() => {
    const allSkills = [...marketSkills, ...localSkills].filter((s) => s.user_invocable !== false);
    return allSkills.filter((skill) => isSkillEnabled(skill.id));
  }, [marketSkills, localSkills, isSkillEnabled]);

  const selectedSkillDetails = useMemo(() => {
    if (!agentConfig?.selectedSkillIds) {
      return [];
    }
    const allSkills = [...marketSkills, ...localSkills].filter((s) => s.user_invocable !== false);
    return allSkills.filter((skill) => agentConfig.selectedSkillIds.includes(skill.id));
  }, [agentConfig, marketSkills, localSkills]);

  const selectedMcpDetails = useMemo(() => {
    if (!agentConfig?.selectedMcpNames) {
      return [];
    }
    return mcpConfigs.filter((mcp) => agentConfig.selectedMcpNames.includes(mcp.name));
  }, [agentConfig, mcpConfigs]);

  // 有可保存为智能体的内容：技能、MCP、指令或浏览器身份域名之一
  const hasSavableConfig =
    (agentConfig?.selectedSkillIds?.length || 0) > 0 ||
    (agentConfig?.selectedMcpNames?.length || 0) > 0 ||
    (agentConfig?.systemPrompt?.trim().length || 0) > 0 ||
    (agentConfig?.autoRestoreDomains?.length || 0) > 0;

  // ==================== Effects ====================

  // 初始化数据加载
  useEffect(() => {
    // 如果 URL 中有 token 参数，说明正在处理 OAuth 回调，跳过加载
    if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('token')) {
      return;
    }

    fetchMarketSkills();
    fetchUserSkillConfig();
    fetchLocalSkillPaths();
    fetchLocalSkills();
    fetchAgents();
  }, [user?.id, fetchMarketSkills, fetchUserSkillConfig, fetchLocalSkillPaths, fetchLocalSkills, fetchAgents]);

  // 监听 actionMode 切换，触发打字机效果
  useEffect(() => {
    const prevMode = prevActionModeRef.current;
    const isSwitchingToAgent = prevMode !== null && prevMode !== 'agent' && actionMode === 'agent';

    if (isSwitchingToAgent) {
      setShowTypewriter(true);
    }

    prevActionModeRef.current = actionMode;
  }, [actionMode]);

  // ==================== Event Handlers ====================

  /** 打字机完成回调 */
  const handleTypewriterComplete = useCallback(() => {
    setShowTypewriter(false);
  }, []);

  /** 打开编辑弹窗 */
  const handleCardClick = useCallback((type: ConfigCardType) => {
    setEditDialogType(type);
    setEditDialogOpen(true);
  }, []);

  /** 保存配置 */
  const handleSaveConfig = useMemo(
    () => createSaveConfigHandler(agentConfig, updateAgentConfig, setAgentConfig, setCurrentBuiltinTools),
    [agentConfig, updateAgentConfig, setAgentConfig, setCurrentBuiltinTools],
  );

  /** 保存为新智能体 */
  const handleSaveAsNewAgent = useCallback(async () => {
    if (isSavingAgent) {
      return;
    }

    if (!hasSavableConfig) {
      toast({
        title: tAgent('configPanel.noConfig'),
        variant: 'destructive',
      });
      return;
    }

    try {
      setIsSavingAgent(true);
      const modelSelection = agentConfig?.modelSelection
        ? {
            providerId: agentConfig.modelSelection.providerId,
            model: agentConfig.modelSelection.model,
            fallbackProviderId: agentConfig.fallbackModelSelection?.providerId,
            fallbackModel: agentConfig.fallbackModelSelection?.model,
            safetyFallbackProviderId: agentConfig.safetyFallbackModelSelection?.providerId,
            safetyFallbackModel: agentConfig.safetyFallbackModelSelection?.model,
          }
        : null;

      const agentData: AgentCreate = {
        name: tAgent('newAgentName'),
        description: '',
        system_prompt: agentConfig?.systemPrompt || '',
        mcp_ids: agentConfig?.selectedMcpNames || [],
        mcp_tool_selections: agentConfig?.mcpToolSelections,
        skill_ids: agentConfig?.selectedSkillIds || [],
        skill_configs: agentConfig?.skillConfigs || {},
        enabled_builtin_tools: currentBuiltinTools,
        browser_source: agentConfig?.browserSource,
        dialog_policy: agentConfig?.dialogPolicy,
        session_recording: agentConfig?.sessionRecording,
        auto_restore_domains: agentConfig?.autoRestoreDomains || [],
        suggestion_prompts: agentConfig?.suggestionPrompts || null,
        model_selection: modelSelection,
        memory_decay_profile: agentConfig?.memoryDecayProfile,
        memory_extraction_preset: agentConfig?.memoryExtractionPreset,
      };
      const newAgent = await createAgent(agentData);
      toast({ title: tAgent('createSuccess') });
      router.push(`/settings/agents?agentId=${newAgent.id}`);
    } catch (error) {
      console.error('创建智能体失败:', error);
      if (!isRiskHeldError(error)) {
        toast({
          title: tAgent('operationFailed'),
          variant: 'destructive',
        });
      }
    } finally {
      setIsSavingAgent(false);
    }
  }, [isSavingAgent, hasSavableConfig, agentConfig, currentBuiltinTools, tAgent, router]);

  const refreshSkills = useCallback(async () => {
    await Promise.all([fetchMarketSkills(), fetchLocalSkills()]);
  }, [fetchMarketSkills, fetchLocalSkills]);

  // ==================== Return Values ====================

  return {
    // State
    isSavingAgent,
    editDialogOpen,
    editDialogType,
    showTypewriter,
    hasSavableConfig,

    // Config
    agentConfig,
    actionMode,
    isConfigPanelExpanded,

    // Data
    enabledSkills,
    enabledMcps,
    selectedSkillDetails,
    selectedMcpDetails,
    currentBuiltinTools,

    // Handlers
    setEditDialogOpen,
    handleCardClick,
    handleSaveConfig,
    handleSaveAsNewAgent,
    handleTypewriterComplete,
    refreshSkills,

    // Translations
    t,
    tIndicator,
  };
};
