/**
 * In-Situ Workflow Skill Picker Types
 * 会话上下文内就地工作流技能即时探索、嵌入式拾取器与动作空间联动类型系统
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 状态机与安全扫描状态严格枚举；
 * 3. 行数严格受控在 200 行以内。
 */

export type SkillSafetyScanStatus = 'clean' | 'pending' | 'warning';

export type NoiseGaugeLevel = 'optimal' | 'moderate' | 'crowded' | 'overloaded';

export interface NoiseGaugeRating {
  score: number; // 0-100
  level: NoiseGaugeLevel;
  totalTokens: number;
  activeToolsCount: number;
  description: string;
}

export interface InSituSkillDescriptor {
  id: string;
  name: string;
  description: string;
  author: string;
  stars: number;
  category: string;
  toolCount: number;
  estimatedTokenCost: number;
  safetyScanStatus: SkillSafetyScanStatus;
  installCmd?: string;
  isMounted: boolean;
  version: string;
  tags: string[];
}

export interface SkillPickerMessagePayload {
  type: 'myrm-skill-pick';
  name: string;
  identifier: string;
  installCmd?: string;
  source?: string;
}

export interface SkillDrawerPosition {
  height: number;
  isOpen: boolean;
}
