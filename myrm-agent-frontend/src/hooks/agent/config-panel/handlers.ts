/**
 * AgentConfigPanel 事件处理器
 *
 * 封装智能体配置面板的保存配置逻辑
 */

import { AgentConfig, DEFAULT_ENABLED_BUILTIN_TOOLS, type BuiltinToolId } from '@/store/chat/types';

/**
 * 保存配置处理器
 */
export const createSaveConfigHandler = (
  agentConfig: AgentConfig | null,
  updateAgentConfig: (config: Partial<AgentConfig>) => void,
  setAgentConfig: (config: AgentConfig) => void,
  setCurrentBuiltinTools: (tools: BuiltinToolId[]) => void,
) => {
  return (data: Partial<AgentConfig>) => {
    // 只有指令内容真的变了才算会话级改写；原样保存不能让服务端放弃智能体已保存的指令
    const promptRewritten = data.systemPrompt !== undefined && data.systemPrompt !== (agentConfig?.systemPrompt ?? '');

    if (agentConfig) {
      updateAgentConfig(promptRewritten ? { ...data, systemPromptEdited: true } : data);
    } else {
      setAgentConfig({
        selectedSkillIds: data.selectedSkillIds || [],
        skillConfigs: data.skillConfigs || {},
        selectedMcpNames: data.selectedMcpNames || [],
        systemPrompt: data.systemPrompt || '',
        systemPromptEdited: promptRewritten,
        useGlobalInstruction: data.useGlobalInstruction ?? true,
        enabledBuiltinTools: data.enabledBuiltinTools ?? [...DEFAULT_ENABLED_BUILTIN_TOOLS],
        autoRestoreDomains: data.autoRestoreDomains || [],
        ephemeralSubagents: data.ephemeralSubagents || {},
      });
    }

    if (data.enabledBuiltinTools) {
      setCurrentBuiltinTools(data.enabledBuiltinTools);
    }
  };
};
