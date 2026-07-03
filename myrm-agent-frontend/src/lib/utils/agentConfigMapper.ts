/**
 * [INPUT]
 * @/services/agent::Agent (POS: Agent 数据模型)
 * @/store/chat/types::AgentConfig, BuiltinToolId (POS: 会话级 Agent 配置类型)
 *
 * [OUTPUT]
 * buildAgentConfig: Agent → AgentConfig 转换函数
 *
 * [POS]
 * Agent 数据模型到会话级配置的标准映射。消除 messageManagement、AgentInfoBanner、usePresetAgent 间的重复映射逻辑。
 */

import type { Agent, AgentModelSelection } from '@/services/agent';
import type { AgentConfig, BuiltinToolId } from '@/store/chat/types';
import type { SingleModelSelection } from '@/store/config/providerTypes';

function toSingleSelection(
  ms: AgentModelSelection | null | undefined,
  pickProvider: 'primary' | 'fallback' | 'safetyFallback',
): SingleModelSelection | undefined {
  if (!ms) return undefined;
  if (pickProvider === 'primary') {
    return ms.providerId && ms.model ? { providerId: ms.providerId, model: ms.model } : undefined;
  }
  if (pickProvider === 'fallback') {
    return ms.fallbackProviderId && ms.fallbackModel
      ? { providerId: ms.fallbackProviderId, model: ms.fallbackModel }
      : undefined;
  }
  return ms.safetyFallbackProviderId && ms.safetyFallbackModel
    ? { providerId: ms.safetyFallbackProviderId, model: ms.safetyFallbackModel }
    : undefined;
}

export function buildAgentConfig(agent: Agent): AgentConfig {
  const ms = agent.model_selection;

  return {
    agentId: agent.id,
    selectedSkillIds: agent.skill_ids ?? [],
    skillConfigs: agent.skill_configs ?? {},
    selectedMcpNames: agent.mcp_ids ?? [],
    systemPrompt: agent.system_prompt ?? '',
    useGlobalInstruction: true,
    autoRestoreDomains: agent.auto_restore_domains ?? [],
    agentName: agent.name,
    agentDescription: agent.description,
    avatarUrl: agent.avatar_url,
    modelSelection: toSingleSelection(ms, 'primary'),
    fallbackModelSelection: toSingleSelection(ms, 'fallback'),
    safetyFallbackModelSelection: toSingleSelection(ms, 'safetyFallback'),
    enabledBuiltinTools: (agent.enabled_builtin_tools ?? undefined) as BuiltinToolId[] | undefined,
    browserSource: agent.browser_source ?? undefined,
    dialogPolicy: (agent.dialog_policy ?? undefined) as AgentConfig['dialogPolicy'],
    sessionRecording: (agent.session_recording ?? undefined) as AgentConfig['sessionRecording'],
    suggestionPrompts: agent.suggestion_prompts ?? undefined,
    memoryDecayProfile: agent.memory_decay_profile,
    mcpToolSelections: agent.mcp_tool_selections,
    commandBindings: agent.command_bindings?.map((b) => ({
      command_name: b.command_name,
      skill_ids: b.skill_ids ?? [],
      description: b.description,
      instruction: b.instruction,
    })),
  };
}
