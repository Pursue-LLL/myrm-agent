/**
 * Skill Action Space Noise Estimator
 * 动作空间噪声计算引擎：评估挂载技能对智能体 Token 预算与工具召回精度的负载
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内；
 * 4. 纯函数确定性算法设计。
 */

import {
  InSituSkillDescriptor,
  NoiseGaugeLevel,
  NoiseGaugeRating,
} from './inSituSkillPickerTypes';

const BASELINE_FRAMEWORK_TOKENS = 600;
const TOKEN_CEILING = 6000;
const TOOL_COUNT_CEILING = 26;

/**
 * 计算一组技能在动作空间中的总 Token 开销、工具总量与拥挤度评级
 */
export function estimateSkillNoise(
  skills: InSituSkillDescriptor[]
): NoiseGaugeRating {
  let totalTokens = BASELINE_FRAMEWORK_TOKENS;
  let activeToolsCount = 0;

  for (const skill of skills) {
    if (skill.isMounted) {
      totalTokens += skill.estimatedTokenCost;
      activeToolsCount += skill.toolCount;
    }
  }

  // 计算拥挤度评分 (0 - 100)
  const tokenRatio = Math.min(1, totalTokens / TOKEN_CEILING);
  const toolRatio = Math.min(1, activeToolsCount / TOOL_COUNT_CEILING);

  // 综合加权评分：Token 占 55%，工具数量占 45%
  const score = Math.round((tokenRatio * 0.55 + toolRatio * 0.45) * 100);

  let level: NoiseGaugeLevel = 'optimal';
  let description = '动作空间极度纯净，工具命中精度与响应速度最佳';

  if (score > 85 || totalTokens > 5500 || activeToolsCount >= 22) {
    level = 'overloaded';
    description = '动作空间严重过载！提示词过长且工具过多，可能导致严重幻觉与推理延迟';
  } else if (score > 68 || totalTokens > 4000 || activeToolsCount >= 16) {
    level = 'crowded';
    description = '动作空间拥挤，边缘工具可能相互干扰，建议精简非必要插件';
  } else if (score > 38 || totalTokens > 2400 || activeToolsCount >= 9) {
    level = 'moderate';
    description = '动作空间负载适中，支持多领域复合任务，保持良好的召回率';
  }

  return {
    score,
    level,
    totalTokens,
    activeToolsCount,
    description,
  };
}

/**
 * 预估若新增挂载一个技能后，动作空间噪声的增量变化
 */
export function estimateDeltaNoise(
  currentSkills: InSituSkillDescriptor[],
  targetSkill: InSituSkillDescriptor
): { before: NoiseGaugeRating; after: NoiseGaugeRating; deltaTokens: number } {
  const before = estimateSkillNoise(currentSkills);

  // 虚拟挂载目标技能
  const nextSkills = currentSkills.map((s) => {
    if (s.id === targetSkill.id) {
      return { ...s, isMounted: true };
    }
    return s;
  });

  // 如果目标技能不在当前列表中，补入并标记已挂载
  if (!nextSkills.some((s) => s.id === targetSkill.id)) {
    nextSkills.push({ ...targetSkill, isMounted: true });
  }

  const after = estimateSkillNoise(nextSkills);
  const deltaTokens = Math.max(0, after.totalTokens - before.totalTokens);

  return {
    before,
    after,
    deltaTokens,
  };
}
