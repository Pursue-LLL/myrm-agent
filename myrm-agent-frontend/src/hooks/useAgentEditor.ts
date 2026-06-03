/**
 * [INPUT]
 * @/services/agent (POS: Agent API 客户端与 Agent DTO 类型)
 * @/hooks/useAgentResources (POS: Agent 资源选择解析 Hook)
 *
 * [OUTPUT]
 * useAgentEditor: Agent 创建/编辑页状态机。
 *
 * [POS]
 * Agent 编辑业务 Hook。集中管理基础信息、能力、安全、人格风格、Subagent 绑定和保存流程。
 */

import { useState, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import useAuthStore from '@/store/useAuthStore';
import useProviderStore from '@/store/useProviderStore';
import { toast } from '@/hooks/useToast';
import {
  Agent,
  AgentModelSelection,
  AgentSessionPolicy,
  DEFAULT_PERSONALITY_STYLE,
  getAgent,
  updateAgent,
  createAgent,
  AgentUpdate,
  AgentCreate,
  OpenAPIServiceConfig,
} from '@/services/agent';
import { DEFAULT_ENABLED_BUILTIN_TOOLS, type BuiltinToolId } from '@/store/chat/types';
import { type ConfigCardType } from '@/components/features/chat-window/agent-config-panel/AgentConfigCards';
import { useAgentResources } from './useAgentResources';

/**
 * 智能体编辑器Hook
 *
 * 管理智能体创建/编辑的所有状态和业务逻辑，包括：
 * - 基本信息（名称、描述、头像）
 * - 能力配置（技能、MCP）
 * - 系统提示词
 * - 表单验证和保存
 *
 * @param agentId 智能体ID（新建时为null）
 * @param isNew 是否是新建模式
 * @param t 翻译函数
 * @returns 智能体数据、表单状态和操作方法
 *
 * @example
 * ```tsx
 * const editor = useAgentEditor(agentId, false, t);
 *
 * // 保存智能体
 * await editor.handleSave();
 *
 * // 开始对话
 * await editor.handleStartChat();
 *
 * // 更新配置
 * editor.handleConfigChange({ selectedSkillIds: ['skill1'] });
 * ```
 */
export function useAgentEditor(agentId: string | null, isNew: boolean, t: (key: string) => string) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, isInitialized } = useAuthStore();

  // Agent数据
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  const isReadonly = agent?.is_built_in === true;

  // 表单状态
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [selectedGradient, setSelectedGradient] = useState(0);

  // 能力配置
  const [selectedSkillIds, setSelectedSkillIds] = useState<string[]>([]);
  const [mountedSkillIds, setMountedSkillIds] = useState<string[]>([]);
  const [selectedMcpNames, setSelectedMcpNames] = useState<string[]>([]);
  const [mcpToolSelections, setMcpToolSelections] = useState<Record<string, string[]>>({});
  const [useGlobalInstruction, setUseGlobalInstruction] = useState(true);
  const [autoRestoreDomains, setAutoRestoreDomains] = useState<string[]>([]);
  const [enabledBuiltinTools, setEnabledBuiltinTools] = useState<BuiltinToolId[]>([...DEFAULT_ENABLED_BUILTIN_TOOLS]);
  const [modelSelection, setModelSelection] = useState<AgentModelSelection | null>(null);

  // 子智能体绑定
  const [selectedSubagentIds, setSelectedSubagentIds] = useState<string[]>([]);

  // 安全策略覆盖
  const [securityOverrides, setSecurityOverrides] = useState<Record<string, unknown> | null>(null);

  // 迭代次数上限
  const [maxIterations, setMaxIterations] = useState<number | null>(null);

  // 记忆遗忘速度
  const [memoryDecayProfile, setMemoryDecayProfile] = useState<'permanent' | 'normal' | 'fast'>('normal');

  // 高级引擎设置
  const [engineParams, setEngineParams] = useState<Record<string, unknown> | null>(null);

  // OpenAPI Services
  const [openapiServices, setOpenapiServices] = useState<OpenAPIServiceConfig[]>([]);

  // Notification targets for channel_notify_tool
  const [notifyTargets, setNotifyTargets] = useState<import('@/services/agent').NotifyTarget[]>([]);

  // Per-agent session policy
  const [sessionPolicy, setSessionPolicy] = useState<AgentSessionPolicy | null>(null);

  // 启发式提示
  const [suggestionPrompts, setSuggestionPrompts] = useState<string[]>([]);

  // Personality 风格
  const [personalityStyle, setPersonalityStyle] = useState<string>(DEFAULT_PERSONALITY_STYLE);

  // 提示模式
  const [promptMode, setPromptMode] = useState<'full' | 'lean' | 'naked'>('full');

  // 可发现性
  const [allowDiscovery, setAllowDiscovery] = useState<boolean>(true);

  // 对话框状态
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editDialogType, setEditDialogType] = useState<ConfigCardType>('skills');

  // System Prompt显示状态
  const [isSystemPromptHidden, setIsSystemPromptHidden] = useState(false);
  const [loadingSystemPrompt, setLoadingSystemPrompt] = useState(false);

  const { enabledSkills, selectedSkillDetails, selectedMcpDetails, enabledMcps } = useAgentResources(
    selectedSkillIds,
    selectedMcpNames,
    mountedSkillIds,
  );

  const [originalData, setOriginalData] = useState({
    name: '',
    description: '',
    systemPrompt: '',
    selectedGradient: 0,
    selectedSkillIds: [] as string[],
    mountedSkillIds: [] as string[],
    selectedMcpNames: [] as string[],
    autoRestoreDomains: [] as string[],
    enabledBuiltinTools: [...DEFAULT_ENABLED_BUILTIN_TOOLS] as BuiltinToolId[],
    modelSelection: null as AgentModelSelection | null,
    selectedSubagentIds: [] as string[],
    securityOverrides: null as Record<string, unknown> | null,
    personalityStyle: DEFAULT_PERSONALITY_STYLE as string,
    promptMode: 'full' as 'full' | 'lean' | 'naked',
    maxIterations: null as number | null,
    memoryDecayProfile: 'normal' as 'permanent' | 'normal' | 'fast',
    engineParams: null as Record<string, unknown> | null,
    openapiServices: [] as OpenAPIServiceConfig[],
    suggestionPrompts: [] as string[],
    sessionPolicy: null as AgentSessionPolicy | null,
    notifyTargets: [] as import('@/services/agent').NotifyTarget[],
    allowDiscovery: true,
  });

  // 检测变更
  useEffect(() => {
    const arraysEqual = (a: string[], b: string[]) => a.length === b.length && a.every((v, i) => v === b[i]);

    const modelChanged =
      modelSelection?.providerId !== originalData.modelSelection?.providerId ||
      modelSelection?.model !== originalData.modelSelection?.model ||
      JSON.stringify(modelSelection?.modelKwargs) !== JSON.stringify(originalData.modelSelection?.modelKwargs);

    const securityChanged = JSON.stringify(securityOverrides) !== JSON.stringify(originalData.securityOverrides);
    const engineParamsChanged = JSON.stringify(engineParams) !== JSON.stringify(originalData.engineParams);
    const openapiChanged = JSON.stringify(openapiServices) !== JSON.stringify(originalData.openapiServices);
    const notifyChanged = JSON.stringify(notifyTargets) !== JSON.stringify(originalData.notifyTargets);
    const sessionPolicyChanged = JSON.stringify(sessionPolicy) !== JSON.stringify(originalData.sessionPolicy);

    const changed =
      name !== originalData.name ||
      description !== originalData.description ||
      systemPrompt !== originalData.systemPrompt ||
      selectedGradient !== originalData.selectedGradient ||
      !arraysEqual(selectedSkillIds, originalData.selectedSkillIds) ||
      !arraysEqual(mountedSkillIds, originalData.mountedSkillIds) ||
      !arraysEqual(selectedMcpNames, originalData.selectedMcpNames) ||
      !arraysEqual(autoRestoreDomains, originalData.autoRestoreDomains) ||
      !arraysEqual(enabledBuiltinTools, originalData.enabledBuiltinTools) ||
      !arraysEqual(selectedSubagentIds, originalData.selectedSubagentIds) ||
      modelChanged ||
      securityChanged ||
      engineParamsChanged ||
      openapiChanged ||
      personalityStyle !== originalData.personalityStyle ||
      promptMode !== originalData.promptMode ||
      memoryDecayProfile !== originalData.memoryDecayProfile ||
      sessionPolicyChanged ||
      notifyChanged ||
      allowDiscovery !== originalData.allowDiscovery ||
      maxIterations !== originalData.maxIterations ||
      !arraysEqual(suggestionPrompts, originalData.suggestionPrompts);
    setHasChanges(changed);
  }, [
    name,
    description,
    systemPrompt,
    selectedGradient,
    selectedSkillIds,
    mountedSkillIds,
    selectedMcpNames,
    autoRestoreDomains,
    enabledBuiltinTools,
    selectedSubagentIds,
    modelSelection,
    securityOverrides,
    personalityStyle,
    promptMode,
    maxIterations,
    memoryDecayProfile,
    openapiServices,
    engineParams,
    suggestionPrompts,
    sessionPolicy,
    notifyTargets,
    originalData,
  ]);

  // 从URL恢复对话框
  useEffect(() => {
    const editType = searchParams.get('editType') as ConfigCardType | null;
    if (editType && ['skills', 'mcp', 'instruction'].includes(editType)) {
      setEditDialogType(editType);
      setEditDialogOpen(true);
    }
  }, [searchParams]);

  // 新建时预填默认模型
  useEffect(() => {
    if (!isNew) return;
    const { defaultModelConfig } = useProviderStore.getState();
    const sel = defaultModelConfig?.baseModel?.primary;
    if (sel) {
      setModelSelection(sel);
      setOriginalData((prev) => ({ ...prev, modelSelection: sel }));
    }
  }, [isNew]);

  // 加载智能体数据
  const reloadAgent = useCallback(async () => {
    if (isNew || !agentId) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      const data = await getAgent(agentId);
      setAgent(data);
      setName(data.name);
      setDescription(data.description || '');
      setSystemPrompt(data.system_prompt || '');

      const gradientMatch = data.avatar_url?.match(/gradient:(\d+)/);
      const gradientIndex = gradientMatch ? parseInt(gradientMatch[1], 10) : 0;
      setSelectedGradient(gradientIndex);

      setSelectedSkillIds(data.skill_ids || []);
      setMountedSkillIds(data.mounted_skill_ids || []);
      setSelectedMcpNames(data.mcp_ids || []);
      setMcpToolSelections(data.mcp_tool_selections || {});
      setAutoRestoreDomains(data.auto_restore_domains || []);
      setSuggestionPrompts(data.suggestion_prompts || []);
      const agentBuiltinTools = (data.enabled_builtin_tools ?? [...DEFAULT_ENABLED_BUILTIN_TOOLS]) as BuiltinToolId[];
      setEnabledBuiltinTools(agentBuiltinTools);
      setModelSelection(data.model_selection ?? null);
      setSecurityOverrides(data.security_overrides ?? null);
      setSelectedSubagentIds(data.subagent_ids || []);
      setPersonalityStyle(data.personality_style || DEFAULT_PERSONALITY_STYLE);
      setPromptMode(data.prompt_mode || 'full');
      setMaxIterations(data.max_iterations ?? null);
      setAllowDiscovery(data.allow_discovery ?? true);
      setMemoryDecayProfile(data.memory_decay_profile || 'normal');
      setEngineParams(data.engine_params ?? null);
      setOpenapiServices((data.openapi_services as OpenAPIServiceConfig[]) || []);
      setSessionPolicy(data.session_policy ?? null);
      setNotifyTargets(data.notify_targets || []);

      setOriginalData({
        name: data.name,
        description: data.description || '',
        systemPrompt: data.system_prompt || '',
        selectedGradient: gradientIndex,
        selectedSkillIds: data.skill_ids || [],
        mountedSkillIds: data.mounted_skill_ids || [],
        selectedMcpNames: data.mcp_ids || [],
        autoRestoreDomains: data.auto_restore_domains || [],
        enabledBuiltinTools: agentBuiltinTools,
        selectedSubagentIds: data.subagent_ids || [],
        modelSelection: data.model_selection ?? null,
        securityOverrides: data.security_overrides ?? null,
        personalityStyle: data.personality_style || DEFAULT_PERSONALITY_STYLE,
        promptMode: data.prompt_mode || 'full',
        allowDiscovery: data.allow_discovery ?? true,
        maxIterations: data.max_iterations ?? null,
        memoryDecayProfile: data.memory_decay_profile || 'normal',
        engineParams: data.engine_params ?? null,
        openapiServices: (data.openapi_services as OpenAPIServiceConfig[]) || [],
        suggestionPrompts: data.suggestion_prompts || [],
        sessionPolicy: data.session_policy ?? null,
        notifyTargets: data.notify_targets || [],
      });
    } catch (error) {
      console.error('Failed to load agent:', error);
      toast({ title: t('agent.loadFailed'), variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [agentId, isNew, t]);

  useEffect(() => {
    void reloadAgent();
  }, [reloadAgent]);

  // 检测system prompt是否被隐藏
  useEffect(() => {
    if (agent && agent.system_prompt === '⚠️ [Hidden for security]') {
      setIsSystemPromptHidden(true);
    } else {
      setIsSystemPromptHidden(false);
    }
  }, [agent]);

  const handleShowSystemPrompt = useCallback(async () => {
    if (!agentId || !agent) return;

    setLoadingSystemPrompt(true);
    try {
      const data = await getAgent(agentId, true);
      const realPrompt = data.system_prompt || '';
      setSystemPrompt(realPrompt);
      setAgent((prev) => (prev ? { ...prev, system_prompt: realPrompt } : null));
      setIsSystemPromptHidden(false);
      toast({ title: t('agent.systemPromptLoaded') });
    } catch (error: unknown) {
      const err = error as { response?: { status?: number } };
      if (err?.response?.status === 403) {
        toast({
          title: t('error'),
          description: t('agent.onlyOwnerCanViewPrompt'),
          variant: 'destructive',
        });
      } else {
        toast({
          title: t('error'),
          description: t('agent.failedToLoadPrompt'),
          variant: 'destructive',
        });
      }
    } finally {
      setLoadingSystemPrompt(false);
    }
  }, [agentId, agent, t]);

  const handleSave = useCallback(async () => {
    if (isReadonly) return;
    if (!name.trim()) {
      toast({ title: t('agent.nameRequired'), variant: 'destructive' });
      return;
    }

    try {
      setSaving(true);

      if (isNew) {
        const createData: AgentCreate = {
          name: name.trim(),
          description: description.trim() || undefined,
          avatar_url: `gradient:${selectedGradient}`,
          system_prompt: systemPrompt.trim() || undefined,
          mcp_ids: selectedMcpNames,
          mcp_tool_selections: Object.keys(mcpToolSelections).length > 0 ? mcpToolSelections : undefined,
          skill_ids: selectedSkillIds,
          mounted_skill_ids: mountedSkillIds,
          enabled_builtin_tools: enabledBuiltinTools,
          auto_restore_domains: autoRestoreDomains,
          suggestion_prompts: suggestionPrompts.length > 0 ? suggestionPrompts : null,
          model_selection: modelSelection,
          security_overrides: securityOverrides,
          prompt_mode: promptMode,
          personality_style: personalityStyle,
          allow_discovery: allowDiscovery,
          subagent_ids: selectedSubagentIds.length > 0 ? selectedSubagentIds : undefined,
          max_iterations: maxIterations,
          memory_decay_profile: memoryDecayProfile,
          session_policy: sessionPolicy,
          engine_params: engineParams,
          openapi_services: openapiServices.length > 0 ? openapiServices : undefined,
          notify_targets: notifyTargets.length > 0 ? notifyTargets : undefined,
        };
        const createdAgent = await createAgent(createData);
        toast({ title: t('agent.createSuccess') });
        router.replace(`/settings/agents?agentId=${createdAgent.id}`);
        return;
      } else if (agent) {
        const updateData: AgentUpdate = {
          name: name.trim(),
          description: description.trim() || undefined,
          avatar_url: `gradient:${selectedGradient}`,
          system_prompt: systemPrompt.trim() || undefined,
          mcp_ids: selectedMcpNames,
          mcp_tool_selections: Object.keys(mcpToolSelections).length > 0 ? mcpToolSelections : undefined,
          skill_ids: selectedSkillIds,
          mounted_skill_ids: mountedSkillIds,
          enabled_builtin_tools: enabledBuiltinTools,
          auto_restore_domains: autoRestoreDomains,
          suggestion_prompts: suggestionPrompts.length > 0 ? suggestionPrompts : null,
          model_selection: modelSelection,
          security_overrides: securityOverrides,
          prompt_mode: promptMode,
          personality_style: personalityStyle,
          allow_discovery: allowDiscovery,
          subagent_ids: selectedSubagentIds.length > 0 ? selectedSubagentIds : [],
          max_iterations: maxIterations,
          memory_decay_profile: memoryDecayProfile,
          session_policy: sessionPolicy,
          engine_params: engineParams,
          openapi_services: openapiServices,
          notify_targets: notifyTargets.length > 0 ? notifyTargets : null,
        };
        const saved = await updateAgent(agent.id, updateData);
        if (saved.snapshot_saved === false) {
          toast({
            title: t('agent.snapshotSaveFailed'),
            description: t('agent.snapshotSaveFailedDesc'),
            variant: 'destructive',
          });
        }

        const refreshed = await getAgent(agent.id);
        setAgent(refreshed);
        setOriginalData({
          name: name.trim(),
          description: description.trim() || '',
          systemPrompt: systemPrompt.trim() || '',
          selectedGradient,
          selectedSkillIds: [...selectedSkillIds],
          mountedSkillIds: [...mountedSkillIds],
          selectedMcpNames: [...selectedMcpNames],
          autoRestoreDomains: [...autoRestoreDomains],
          enabledBuiltinTools: [...enabledBuiltinTools],
          selectedSubagentIds: [...selectedSubagentIds],
          modelSelection,
          securityOverrides,
          personalityStyle,
          allowDiscovery,
          promptMode,
          maxIterations,
          memoryDecayProfile,
          engineParams,
          openapiServices: [...openapiServices],
          suggestionPrompts: [...suggestionPrompts],
          sessionPolicy,
          notifyTargets: [...notifyTargets],
        });
        toast({ title: t('agent.updateSuccess') });
      }

      setHasChanges(false);
    } catch (error) {
      toast({ title: t('agent.operationFailed'), variant: 'destructive' });
      throw error;
    } finally {
      setSaving(false);
    }
  }, [
    agent,
    isNew,
    isReadonly,
    name,
    description,
    systemPrompt,
    selectedGradient,
    selectedSkillIds,
    mountedSkillIds,
    selectedMcpNames,
    enabledBuiltinTools,
    autoRestoreDomains,
    selectedSubagentIds,
    securityOverrides,
    personalityStyle,
    promptMode,
    maxIterations,
    memoryDecayProfile,
    engineParams,
    openapiServices,
    suggestionPrompts,
    notifyTargets,
    modelSelection,
    router,
    t,
  ]);

  const handleStartChat = useCallback(async () => {
    if (!name.trim()) {
      toast({ title: t('agent.nameRequired'), variant: 'destructive' });
      return;
    }

    if (isNew && !agent) {
      try {
        await handleSave();
      } catch {
        return;
      }
    } else if (agent && hasChanges) {
      try {
        await handleSave();
      } catch {
        return;
      }
    }

    if (agent) {
      router.push(`/?agent_id=${agent.id}`);
    }
  }, [agent, hasChanges, name, isNew, handleSave, router, t]);

  const handleConfigChange = useCallback(
    (data: {
      selectedSkillIds?: string[];
      mountedSkillIds?: string[];
      selectedMcpNames?: string[];
      mcpToolSelections?: Record<string, string[]>;
      systemPrompt?: string;
      useGlobalInstruction?: boolean;
      enabledBuiltinTools?: BuiltinToolId[];
      autoRestoreDomains?: string[];
    }) => {
      if (data.selectedSkillIds !== undefined) setSelectedSkillIds(data.selectedSkillIds);
      if (data.mountedSkillIds !== undefined) setMountedSkillIds(data.mountedSkillIds);
      if (data.selectedMcpNames !== undefined) setSelectedMcpNames(data.selectedMcpNames);
      if (data.mcpToolSelections !== undefined) setMcpToolSelections(data.mcpToolSelections);
      if (data.systemPrompt !== undefined) setSystemPrompt(data.systemPrompt);
      if (data.useGlobalInstruction !== undefined) setUseGlobalInstruction(data.useGlobalInstruction);
      if (data.enabledBuiltinTools !== undefined) setEnabledBuiltinTools(data.enabledBuiltinTools);
      if (data.autoRestoreDomains !== undefined) setAutoRestoreDomains(data.autoRestoreDomains);
    },
    [],
  );

  return {
    // 状态
    agent,
    loading,
    saving,
    hasChanges,
    isReadonly,
    user,
    isInitialized,
    // 表单
    name,
    setName,
    description,
    setDescription,
    systemPrompt,
    selectedGradient,
    setSelectedGradient,
    // 能力
    selectedSkillIds,
    mountedSkillIds,
    selectedMcpNames,
    mcpToolSelections,
    autoRestoreDomains,
    setAutoRestoreDomains,
    suggestionPrompts,
    setSuggestionPrompts,
    enabledBuiltinTools,
    useGlobalInstruction,
    selectedSkillDetails,
    selectedMcpDetails,
    modelSelection,
    setModelSelection,
    // 子智能体
    selectedSubagentIds,
    setSelectedSubagentIds,
    // 安全策略
    securityOverrides,
    setSecurityOverrides,
    // Personality
    personalityStyle,
    setPersonalityStyle,
    // 提示模式
    promptMode,
    setPromptMode,
    // 可发现性
    allowDiscovery,
    setAllowDiscovery,
    // 迭代次数
    maxIterations,
    setMaxIterations,
    // 记忆遗忘速度
    memoryDecayProfile,
    setMemoryDecayProfile,
    // 高级引擎设置
    engineParams,
    setEngineParams,
    // OpenAPI Services
    openapiServices,
    setOpenapiServices,
    // Notification targets
    notifyTargets,
    setNotifyTargets,
    // Session Policy
    sessionPolicy,
    setSessionPolicy,
    // 数据
    enabledSkills,
    enabledMcps,
    // 对话框
    editDialogOpen,
    setEditDialogOpen,
    editDialogType,
    setEditDialogType,
    // 操作
    handleSave,
    handleStartChat,
    handleConfigChange,
    // System Prompt控制
    isSystemPromptHidden,
    loadingSystemPrompt,
    handleShowSystemPrompt,
    reloadAgent,
    snapshotCount: agent?.snapshot_count ?? 0,
  };
}
