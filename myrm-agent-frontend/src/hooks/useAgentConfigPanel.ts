import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import useAgentStore from '@/store/useAgentStore';
import { useSkillStore } from '@/store/skill';
import useAuthStore from '@/store/useAuthStore';
import { getAgent, createAgent, updateAgent, AgentCreate, AgentUpdate } from '@/services/agent';
import { AgentConfig, DEFAULT_ENABLED_BUILTIN_TOOLS, type BuiltinToolId } from '@/store/chat/types';
import { toast } from '@/hooks/useToast';
import { usePresetAgent } from '@/hooks/usePresetAgent';
import type { ConfigCardType } from '@/components/features/chat-window/agent-config-panel/AgentConfigCards';
import { createSaveConfigHandler } from './use-agent-config-panel/handlers';

/**
 * AgentConfigPanel 业务逻辑Hook
 *
 * 封装智能体配置面板的所有状态管理和业务逻辑，包括：
 * - Store集成（Chat, Config, Skill, Agent, Auth）
 * - 本地状态管理（对话框、加载状态、打字机效果）
 * - 数据计算（已启用技能、选中详情、配置变化检测）
 * - 事件处理（选择智能体、保存配置、更新智能体）
 *
 * @example
 * ```tsx
 * function AgentConfigPanel() {
 *   const {
 *     agentConfig,
 *     enabledSkills,
 *     handleCardClick,
 *     handleSaveConfig,
 *   } = useAgentConfigPanel();
 *
 *   return <UI {...props} />;
 * }
 * ```
 *
 * @returns {Object} Hook返回值
 * @returns {boolean} returns.isLoading - 数据加载中
 * @returns {boolean} returns.isSavingAgent - 保存智能体中
 * @returns {boolean} returns.editDialogOpen - 编辑对话框开关
 * @returns {ConfigCardType} returns.editDialogType - 编辑对话框类型
 * @returns {boolean} returns.showTypewriter - 显示打字机欢迎消息
 * @returns {boolean} returns.hasConfigChanges - 配置是否有变化
 * @returns {AgentConfig | null} returns.agentConfig - 当前智能体配置
 * @returns {string} returns.actionMode - 当前动作模式
 * @returns {boolean} returns.isConfigPanelExpanded - 配置面板展开状态
 * @returns {Array} returns.enabledSkills - 已启用的技能列表
 * @returns {Array} returns.enabledMcps - 已启用的MCP列表
 * @returns {Array} returns.selectedSkillDetails - 选中技能的详情
 * @returns {Array} returns.selectedMcpDetails - 选中MCP的详情
 * @returns {string | null} returns.selectedPresetId - 选中的预置智能体ID
 * @returns {Function} returns.setEditDialogOpen - 设置编辑对话框状态
 * @returns {Function} returns.handleCardClick - 处理卡片点击事件
 * @returns {Function} returns.handleSaveConfig - 保存配置
 * @returns {Function} returns.handleSaveAsNewAgent - 保存为新智能体
 * @returns {Function} returns.handleUpdateAgent - 更新已保存的智能体
 * @returns {Function} returns.handleSelectAgent - 选择智能体
 * @returns {Function} returns.handleSelectPreset - 选择预置智能体
 * @returns {Function} returns.clearPresetSelection - 清除预置选择
 * @returns {Function} returns.handleTypewriterComplete - 打字机完成回调
 * @returns {Function} returns.t - 翻译函数（configPanel）
 * @returns {Function} returns.tAgent - 翻译函数（agent）
 * @returns {Function} returns.tIndicator - 翻译函数（indicator）
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
  const { fetchAgents, updateAgentStore } = useAgentStore(
    useShallow((state) => ({
      fetchAgents: state.fetchAgents,
      updateAgentStore: state.update,
    })),
  );

  // Auth store
  const user = useAuthStore((state) => state.user);

  // ==================== Local State ====================

  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editDialogType, setEditDialogType] = useState<ConfigCardType>('skills');
  const [isLoading, setIsLoading] = useState(false);
  const [isSavingAgent, setIsSavingAgent] = useState(false);

  // 打字机欢迎消息状态
  const [showTypewriter, setShowTypewriter] = useState(false);
  const prevActionModeRef = useRef<string | null>(null);

  // 记录智能体的原始配置，用于检测是否有变化
  const originalAgentConfigRef = useRef<{
    agentId: string;
    selectedSkillIds: string[];
    skillConfigs?: Record<string, { is_core?: boolean }>;
    selectedMcpNames: string[];
    systemPrompt: string;
    autoRestoreDomains: string[];
    enabledBuiltinTools: BuiltinToolId[];
    memoryDecayProfile?: 'permanent' | 'normal' | 'fast';
  } | null>(null);

  // 使用预置智能体 Hook
  const { selectedPresetId, handleSelectPreset, clearPresetSelection } = usePresetAgent({
    setAgentConfig,
    originalAgentConfigRef,
  });

  // ==================== Memoized Values ====================

  // 获取已启用的技能详情（包括市场技能、个人技能和本地技能，排除 user_invocable=false）
  const enabledSkills = useMemo(() => {
    const allSkills = [...marketSkills, ...localSkills].filter((s) => s.user_invocable !== false);
    return allSkills.filter((skill) => isSkillEnabled(skill.id));
  }, [marketSkills, localSkills, isSkillEnabled]);

  const selectedSkillDetails = useMemo(() => {
    if (!agentConfig?.selectedSkillIds) return [];
    const allSkills = [...marketSkills, ...localSkills].filter((s) => s.user_invocable !== false);
    return allSkills.filter((skill) => agentConfig.selectedSkillIds.includes(skill.id));
  }, [agentConfig, marketSkills, localSkills]);

  const selectedMcpDetails = useMemo(() => {
    if (!agentConfig?.selectedMcpNames) return [];
    return mcpConfigs.filter((mcp) => agentConfig.selectedMcpNames.includes(mcp.name));
  }, [agentConfig, mcpConfigs]);

  // 检测当前配置是否相对于已保存的智能体有变化
  const hasConfigChanges = useMemo(() => {
    // 如果没有智能体 ID，说明是新配置，不需要检测变化
    if (!agentConfig?.agentId) return false;
    // 如果没有原始配置引用，说明还没有加载过智能体
    if (!originalAgentConfigRef.current) return false;
    // 如果 agentId 不匹配，说明切换了智能体
    if (originalAgentConfigRef.current.agentId !== agentConfig.agentId) return false;

    const original = originalAgentConfigRef.current;
    const current = agentConfig;

    // 比较技能
    const origSkills = original.selectedSkillIds ?? [];
    const currSkills = current.selectedSkillIds ?? [];
    const skillsChanged = origSkills.length !== currSkills.length || !origSkills.every((id) => currSkills.includes(id));

    // 比较 MCP
    const origMcps = original.selectedMcpNames ?? [];
    const currMcps = current.selectedMcpNames ?? [];
    const mcpsChanged = origMcps.length !== currMcps.length || !origMcps.every((name) => currMcps.includes(name));

    // 比较系统指令
    const promptChanged = original.systemPrompt !== (current.systemPrompt || '');

    // 比较自动恢复域名
    const origDomains = original.autoRestoreDomains ?? [];
    const currDomains = current.autoRestoreDomains ?? [];
    const autoRestoreDomainsChanged =
      origDomains.length !== currDomains.length || !origDomains.every((domain) => currDomains.includes(domain));

    // 比较内置工具（对比 session-level 与原始持久化配置）
    const origBuiltins = original.enabledBuiltinTools ?? [];
    const builtinToolsChanged =
      origBuiltins.length !== currentBuiltinTools.length ||
      !origBuiltins.every((id) => currentBuiltinTools.includes(id));

    // 比较记忆遗忘速度
    const memoryDecayChanged = (original.memoryDecayProfile || 'normal') !== (current.memoryDecayProfile || 'normal');

    return (
      skillsChanged ||
      mcpsChanged ||
      promptChanged ||
      autoRestoreDomainsChanged ||
      builtinToolsChanged ||
      memoryDecayChanged
    );
  }, [agentConfig, currentBuiltinTools]);

  // ==================== Effects ====================

  // 初始化数据加载
  useEffect(() => {
    // 如果 URL 中有 token 参数，说明正在处理 OAuth 回调，跳过加载
    if (typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.has('token')) {
        return;
      }
    }

    const loadData = async () => {
      setIsLoading(true);
      try {
        fetchMarketSkills();
        fetchUserSkillConfig();
        fetchLocalSkillPaths();
        fetchLocalSkills();

        fetchAgents();
      } catch (error) {
        console.error('加载智能体配置数据失败:', error);
      } finally {
        setIsLoading(false);
      }
    };

    loadData();
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
  const handleSaveConfig = useCallback(
    createSaveConfigHandler(agentConfig, updateAgentConfig, setAgentConfig, setCurrentBuiltinTools),
    [agentConfig, updateAgentConfig, setAgentConfig, setCurrentBuiltinTools],
  );

  /** 保存为新智能体 */
  const handleSaveAsNewAgent = useCallback(async () => {
    if (isSavingAgent) return;

    // 检查是否有配置
    const hasConfig =
      (agentConfig?.selectedSkillIds?.length || 0) > 0 ||
      (agentConfig?.selectedMcpNames?.length || 0) > 0 ||
      (agentConfig?.systemPrompt?.trim().length || 0) > 0 ||
      (agentConfig?.autoRestoreDomains?.length || 0) > 0;

    if (!hasConfig) {
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
        skill_ids: agentConfig?.selectedSkillIds || [],
        skill_configs: agentConfig?.skillConfigs || {},
        enabled_builtin_tools: currentBuiltinTools,
        auto_restore_domains: agentConfig?.autoRestoreDomains || [],
        suggestion_prompts: agentConfig?.suggestionPrompts || null,
        model_selection: modelSelection,
        memory_decay_profile: agentConfig?.memoryDecayProfile,
      };
      const newAgent = await createAgent(agentData);
      toast({ title: tAgent('createSuccess') });
      router.push(`/settings/agents?agentId=${newAgent.id}`);
    } catch (error) {
      console.error('创建智能体失败:', error);
      toast({
        title: tAgent('operationFailed'),
        variant: 'destructive',
      });
    } finally {
      setIsSavingAgent(false);
    }
  }, [isSavingAgent, agentConfig, currentBuiltinTools, tAgent, router]);

  /** 更新已保存的智能体 */
  const handleUpdateAgent = useCallback(async () => {
    if (isSavingAgent || !agentConfig?.agentId) return;

    try {
      setIsSavingAgent(true);
      const modelSelection = agentConfig.modelSelection
        ? {
            providerId: agentConfig.modelSelection.providerId,
            model: agentConfig.modelSelection.model,
            fallbackProviderId: agentConfig.fallbackModelSelection?.providerId,
            fallbackModel: agentConfig.fallbackModelSelection?.model,
            safetyFallbackProviderId: agentConfig.safetyFallbackModelSelection?.providerId,
            safetyFallbackModel: agentConfig.safetyFallbackModelSelection?.model,
          }
        : null;

      const agentData: AgentUpdate = {
        system_prompt: agentConfig.systemPrompt || '',
        mcp_ids: agentConfig.selectedMcpNames || [],
        skill_ids: agentConfig.selectedSkillIds || [],
        skill_configs: agentConfig.skillConfigs || {},
        enabled_builtin_tools: currentBuiltinTools,
        auto_restore_domains: agentConfig.autoRestoreDomains || [],
        suggestion_prompts: agentConfig.suggestionPrompts || null,
        model_selection: modelSelection,
        memory_decay_profile: agentConfig.memoryDecayProfile,
      };
      await updateAgent(agentConfig.agentId, agentData);

      originalAgentConfigRef.current = {
        agentId: agentConfig.agentId,
        selectedSkillIds: agentConfig.selectedSkillIds || [],
        skillConfigs: agentConfig.skillConfigs || {},
        selectedMcpNames: agentConfig.selectedMcpNames || [],
        systemPrompt: agentConfig.systemPrompt || '',
        autoRestoreDomains: [...(agentConfig.autoRestoreDomains || [])],
        enabledBuiltinTools: [...currentBuiltinTools],
      };

      // 更新 store 中的智能体数据
      updateAgentStore(agentConfig.agentId, agentData);

      toast({ title: tAgent('updateSuccess') });
    } catch (error) {
      console.error('更新智能体失败:', error);
      toast({
        title: tAgent('operationFailed'),
        variant: 'destructive',
      });
    } finally {
      setIsSavingAgent(false);
    }
  }, [isSavingAgent, agentConfig, currentBuiltinTools, tAgent, updateAgentStore]);

  /** 选择已保存的智能体 */
  const handleSelectAgent = useCallback(
    async (agent: { id: string }) => {
      try {
        const agentDetail = await getAgent(agent.id);
        const builtinTools = (agentDetail.enabled_builtin_tools ?? [
          ...DEFAULT_ENABLED_BUILTIN_TOOLS,
        ]) as BuiltinToolId[];
        const newConfig: AgentConfig = {
          agentId: agentDetail.id,
          agentName: agentDetail.name,
          avatarUrl: agentDetail.avatar_url,
          selectedSkillIds: agentDetail.skill_ids || [],
          skillConfigs: agentDetail.skill_configs || {},
          selectedMcpNames: agentDetail.mcp_ids || [],
          systemPrompt: agentDetail.system_prompt || '',
          useGlobalInstruction: true,
          autoRestoreDomains: agentDetail.auto_restore_domains || [],
          suggestionPrompts: agentDetail.suggestion_prompts || undefined,
          enabledBuiltinTools: builtinTools,
          modelSelection: agentDetail.model_selection ?? null,
          fallbackModelSelection:
            agentDetail.model_selection?.fallbackProviderId && agentDetail.model_selection?.fallbackModel
              ? {
                  providerId: agentDetail.model_selection.fallbackProviderId,
                  model: agentDetail.model_selection.fallbackModel,
                }
              : null,
          safetyFallbackModelSelection:
            agentDetail.model_selection?.safetyFallbackProviderId && agentDetail.model_selection?.safetyFallbackModel
              ? {
                  providerId: agentDetail.model_selection.safetyFallbackProviderId,
                  model: agentDetail.model_selection.safetyFallbackModel,
                }
              : null,
          memoryDecayProfile: agentDetail.memory_decay_profile || 'normal',
          browserSource: agentDetail.browser_source || undefined,
        };
        setAgentConfig(newConfig);

        originalAgentConfigRef.current = {
          agentId: agentDetail.id,
          selectedSkillIds: agentDetail.skill_ids || [],
          skillConfigs: agentDetail.skill_configs || {},
          selectedMcpNames: agentDetail.mcp_ids || [],
          systemPrompt: agentDetail.system_prompt || '',
          autoRestoreDomains: agentDetail.auto_restore_domains || [],
          enabledBuiltinTools: builtinTools,
          memoryDecayProfile: agentDetail.memory_decay_profile || 'normal',
        };
      } catch (error) {
        console.error('加载智能体详情失败:', error);
        toast({
          title: tAgent('loadAgentFailed'),
          variant: 'destructive',
        });
      }
    },
    [setAgentConfig, tAgent],
  );

  // ==================== Return Values ====================

  return {
    // State
    isLoading,
    isSavingAgent,
    editDialogOpen,
    editDialogType,
    showTypewriter,
    hasConfigChanges,

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

    // Preset
    selectedPresetId,

    // Handlers
    setEditDialogOpen,
    handleCardClick,
    handleSaveConfig,
    handleSaveAsNewAgent,
    handleUpdateAgent,
    handleSelectAgent,
    handleSelectPreset,
    clearPresetSelection,
    handleTypewriterComplete,

    // Translations
    t,
    tAgent,
    tIndicator,
  };
};
