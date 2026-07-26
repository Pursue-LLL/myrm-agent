/**
 * Agent 配置变更检测
 *
 * 对比 DB 原始快照与当前内存态的 AgentConfig，判断是否存在未保存的变更。
 * 纯函数，便于单元测试。
 */

import type { BuiltinToolId } from '@/store/chat/types';

export interface OriginalAgentSnapshot {
  agentId: string;
  selectedSkillIds: string[];
  skillConfigs?: Record<string, { is_core?: boolean }>;
  selectedMcpNames: string[];
  systemPrompt: string;
  autoRestoreDomains: string[];
  enabledBuiltinTools: BuiltinToolId[];
  memoryDecayProfile?: 'permanent' | 'normal' | 'fast';
  modelSelection?: { providerId: string; model: string } | null;
  fallbackModelSelection?: { providerId: string; model: string } | null;
  safetyFallbackModelSelection?: { providerId: string; model: string } | null;
}

interface CurrentAgentState {
  agentId?: string;
  selectedSkillIds: string[];
  selectedMcpNames: string[];
  systemPrompt: string;
  autoRestoreDomains?: string[];
  memoryDecayProfile?: 'permanent' | 'normal' | 'fast';
  modelSelection?: { providerId: string; model: string } | null;
  fallbackModelSelection?: { providerId: string; model: string } | null;
  safetyFallbackModelSelection?: { providerId: string; model: string } | null;
}

/**
 * 检测 Agent 配置是否相对于 DB 原始快照有变更。
 *
 * @returns true 表示有未保存的变更
 */
export function detectAgentConfigChanges(
  original: OriginalAgentSnapshot | null,
  current: CurrentAgentState | null,
  currentBuiltinTools: BuiltinToolId[],
): boolean {
  if (!current?.agentId) return false;
  if (!original) return false;
  if (original.agentId !== current.agentId) return false;

  const arraysEqual = (a: string[], b: string[]) =>
    a.length === b.length && a.every((v) => b.includes(v));

  const skillsChanged = !arraysEqual(
    original.selectedSkillIds ?? [],
    current.selectedSkillIds ?? [],
  );

  const mcpsChanged = !arraysEqual(
    original.selectedMcpNames ?? [],
    current.selectedMcpNames ?? [],
  );

  const promptChanged = original.systemPrompt !== (current.systemPrompt || '');

  const autoRestoreDomainsChanged = !arraysEqual(
    original.autoRestoreDomains ?? [],
    current.autoRestoreDomains ?? [],
  );

  const builtinToolsChanged = !arraysEqual(
    original.enabledBuiltinTools ?? [],
    currentBuiltinTools,
  );

  const memoryDecayChanged =
    (original.memoryDecayProfile || 'normal') !== (current.memoryDecayProfile || 'normal');

  const modelSelectionChanged =
    (original.modelSelection?.providerId ?? '') !== (current.modelSelection?.providerId ?? '') ||
    (original.modelSelection?.model ?? '') !== (current.modelSelection?.model ?? '');

  const fallbackModelChanged =
    (original.fallbackModelSelection?.providerId ?? '') !==
      (current.fallbackModelSelection?.providerId ?? '') ||
    (original.fallbackModelSelection?.model ?? '') !==
      (current.fallbackModelSelection?.model ?? '');

  const safetyFallbackModelChanged =
    (original.safetyFallbackModelSelection?.providerId ?? '') !==
      (current.safetyFallbackModelSelection?.providerId ?? '') ||
    (original.safetyFallbackModelSelection?.model ?? '') !==
      (current.safetyFallbackModelSelection?.model ?? '');

  return (
    skillsChanged ||
    mcpsChanged ||
    promptChanged ||
    autoRestoreDomainsChanged ||
    builtinToolsChanged ||
    memoryDecayChanged ||
    modelSelectionChanged ||
    fallbackModelChanged ||
    safetyFallbackModelChanged
  );
}
