/**
 * [INPUT]
 * @/types/agentSkillConfig::AgentSkillConfigMap (POS: Agent 技能个性化配置类型)
 *
 * [OUTPUT]
 * areSkillConfigsEqual: 两份技能个性化配置语义相等判断
 *
 * [POS]
 * 技能个性化配置（is_core / instance_name）的比较。缺省字段按默认值（false / null）计，键顺序无关，
 * 供 Agent 编辑页判断技能配置是否有未保存的改动。
 */

import type { AgentSkillConfigMap } from '@/types/agentSkillConfig';

function normalizeSkillConfigs(configs: AgentSkillConfigMap | undefined): AgentSkillConfigMap {
  if (!configs) {
    return {};
  }
  const normalized: AgentSkillConfigMap = {};
  for (const [skillId, cfg] of Object.entries(configs)) {
    normalized[skillId] = {
      is_core: cfg?.is_core ?? false,
      instance_name: cfg?.instance_name ?? null,
    };
  }
  return normalized;
}

export function areSkillConfigsEqual(
  left: AgentSkillConfigMap | undefined,
  right: AgentSkillConfigMap | undefined,
): boolean {
  const normalizedLeft = normalizeSkillConfigs(left);
  const normalizedRight = normalizeSkillConfigs(right);
  const leftKeys = Object.keys(normalizedLeft).sort();
  const rightKeys = Object.keys(normalizedRight).sort();
  if (leftKeys.length !== rightKeys.length) {
    return false;
  }
  return leftKeys.every((key, index) => {
    if (key !== rightKeys[index]) {
      return false;
    }
    const a = normalizedLeft[key];
    const b = normalizedRight[key];
    return a.is_core === b.is_core && (a.instance_name ?? null) === (b.instance_name ?? null);
  });
}
