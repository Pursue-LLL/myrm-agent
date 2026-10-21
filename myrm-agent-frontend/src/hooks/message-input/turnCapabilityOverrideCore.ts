/**
 * [INPUT]
 * - @/store/chat/types::AgentConfig (POS: 会话级 Agent 与模式配置类型)
 *
 * [OUTPUT]
 * - TurnCapabilitySelection: 单轮能力选择契约。
 * - resolveEffectiveTurnSelection: 解析基线+选择后的有效子集。
 * - normalizeTurnCapabilitySelection: 归一化单轮子集（全选折叠为 null）。
 * - buildTurnAgentConfigOverride: 构建一次性 `agentConfigOverride`。
 *
 * [POS]
 * 聊天输入链路的单轮能力覆写核心。负责把 Skill/MCP 子集选择转换为稳定、最小化且可发送的配置覆盖对象。
 */
import type { AgentConfig } from '@/store/chat/types';

export interface TurnCapabilitySelection {
  skillIds: string[] | null;
  mcpNames: string[] | null;
}

function uniqueValues(values: readonly string[]): string[] {
  return Array.from(new Set(values));
}

export function resolveEffectiveTurnSelection(
  baseValues: readonly string[],
  selectedValues: readonly string[] | null,
): string[] {
  const base = uniqueValues(baseValues);
  if (selectedValues === null) {
    return base;
  }
  const selectedSet = new Set(uniqueValues(selectedValues));
  return base.filter((value) => selectedSet.has(value));
}

function normalizeSubset(baseValues: readonly string[], selectedValues: readonly string[] | null): string[] | null {
  const base = uniqueValues(baseValues);
  if (base.length === 0 || selectedValues === null) {
    return null;
  }
  const selected = uniqueValues(selectedValues);
  const effective = resolveEffectiveTurnSelection(base, selected);
  // Guard stale selections (all removed/renamed) from silently becoming "disable all".
  if (selected.length > 0 && effective.length === 0) {
    return null;
  }
  if (effective.length === base.length) {
    return null;
  }
  return effective;
}

export function normalizeTurnCapabilitySelection(
  baseSkillIds: readonly string[],
  baseMcpNames: readonly string[],
  selectedSkillIds: readonly string[] | null,
  selectedMcpNames: readonly string[] | null,
): TurnCapabilitySelection | null {
  const normalizedSkills = normalizeSubset(baseSkillIds, selectedSkillIds);
  const normalizedMcps = normalizeSubset(baseMcpNames, selectedMcpNames);
  if (normalizedSkills === null && normalizedMcps === null) {
    return null;
  }
  return {
    skillIds: normalizedSkills,
    mcpNames: normalizedMcps,
  };
}

export function buildTurnAgentConfigOverride(
  agentConfig: AgentConfig | null,
  selection: TurnCapabilitySelection | null,
): AgentConfig | null {
  if (!agentConfig || !selection) {
    return null;
  }

  const normalized = normalizeTurnCapabilitySelection(
    agentConfig.selectedSkillIds ?? [],
    agentConfig.selectedMcpNames ?? [],
    selection.skillIds,
    selection.mcpNames,
  );
  if (!normalized) {
    return null;
  }

  return {
    ...agentConfig,
    selectedSkillIds: normalized.skillIds ?? uniqueValues(agentConfig.selectedSkillIds ?? []),
    selectedMcpNames: normalized.mcpNames ?? uniqueValues(agentConfig.selectedMcpNames ?? []),
  };
}
