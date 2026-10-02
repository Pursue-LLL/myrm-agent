/**
 * 智能体配置依赖校验工具
 * 用于检查智能体配置中的技能、MCP 是否仍然存在
 */

import type { Skill } from '@/store/skill/types';
import type { MCPServiceConfig } from '@/store/config/types';
import type { Agent } from '@/services/agent';

type AgentDependencyConfig = Pick<Agent, 'skill_ids' | 'mcp_ids'>;

export interface ValidationResult {
  isValid: boolean;
  missingSkills: string[];
  missingMcps: string[];
}

/**
 * 校验智能体依赖是否仍然有效
 *
 * @param agent - 智能体配置
 * @param allSkills - 所有可用的技能列表
 * @param mcpConfigs - 所有可用的 MCP 配置
 * @returns 校验结果
 */
export function validateAgentDependencies(
  agent: AgentDependencyConfig,
  allSkills: Skill[],
  mcpConfigs: MCPServiceConfig[],
): ValidationResult {
  const missingSkills = (agent.skill_ids || []).filter((id) => !allSkills.some((s) => s.id === id));

  const missingMcps = (agent.mcp_ids || []).filter((name) => !mcpConfigs.some((m) => m.name === name));

  return {
    isValid: missingSkills.length === 0 && missingMcps.length === 0,
    missingSkills,
    missingMcps,
  };
}

/**
 * 构建依赖失效消息的各部分
 * 返回翻译键和参数，供调用方使用具体的翻译函数
 */
export function buildMissingDependenciesParts(result: ValidationResult): Array<{ key: string; count: number }> {
  const parts: Array<{ key: string; count: number }> = [];

  if (result.missingSkills.length > 0) {
    parts.push({ key: 'validation.missingSkills', count: result.missingSkills.length });
  }
  if (result.missingMcps.length > 0) {
    parts.push({ key: 'validation.missingMcps', count: result.missingMcps.length });
  }

  return parts;
}
