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
  return (data: {
    selectedSkillIds?: string[];
    skillConfigs?: Record<string, { is_core?: boolean }>;
    selectedMcpNames?: string[];
    mcpToolSelections?: Record<string, string[]>;
    systemPrompt?: string;
    useGlobalInstruction?: boolean;
    enabledBuiltinTools?: BuiltinToolId[];
    autoRestoreDomains?: string[];
    ephemeralSubagents?: Record<string, unknown>;
    personalityStyle?: string;
  }) => {
    if (agentConfig) {
      updateAgentConfig(data);
    } else {
      setAgentConfig({
        selectedSkillIds: data.selectedSkillIds || [],
        skillConfigs: data.skillConfigs || {},
        selectedMcpNames: data.selectedMcpNames || [],
        systemPrompt: data.systemPrompt || '',
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
