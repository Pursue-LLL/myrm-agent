/**
 * Skill (技能) 展现与描述守卫工具函数
 *
 * 为缺少描述或描述为空白的技能提供安全优雅的降级占位，
 * 防止 SkillCard、SkillDetailSheet 等组件高度塌陷或硬编码英文破坏排版。
 */

export interface SkillLikeWithDescription {
  description?: string | null;
  [key: string]: unknown;
}

/**
 * 安全解析技能描述。如果技能缺失描述或为空白字符，返回多语言降级文本。
 *
 * @param skill 技能对象
 * @param fallbackText 缺省占位文案 (通常来自 i18n t('skills.noDescription') 或本地化翻译)
 * @returns 规整后的技能描述字符串
 */
export function resolveSkillDescription(
  skill: SkillLikeWithDescription | null | undefined,
  fallbackText = 'No description provided',
): string {
  if (!skill) {
    return fallbackText;
  }
  const desc = typeof skill.description === 'string' ? skill.description.trim() : '';
  return desc || fallbackText;
}
