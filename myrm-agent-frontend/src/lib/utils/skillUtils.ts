/**
 * Skill (技能) 展现、描述守卫与搜索命中工具函数
 *
 * 为缺少描述或描述为空白的技能提供安全优雅的降级占位，
 * 防止 SkillCard、SkillDetailSheet 等组件高度塌陷或硬编码英文破坏排版；
 * 并给出已安装技能列表搜索的唯一命中规则。
 */

export interface SkillLikeWithDescription {
  description?: string | null;
}

/**
 * 安全解析技能描述。如果技能缺失描述或为空白字符，返回多语言降级文本。
 *
 * @param skill 技能对象
 * @param fallbackText 缺省占位文案 (通常来自 i18n 如 noDescription 或本地化翻译)
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

export interface SkillSearchFields {
  name: string;
  description: string;
  tags: string[];
  storage_path: string;
}

/** 技能目录名：健康度与趋势面板用它称呼技能，可能与技能声明的 name 不同。 */
function skillFolderName(storagePath: string): string {
  return storagePath.split(/[\\/]/).filter(Boolean).pop() ?? '';
}

/**
 * 已安装技能的搜索命中规则：名称、描述、标签或目录名包含查询词（不区分大小写）。
 * 只比对目录名而非整条路径，避免上级目录（用户名、skills）让所有技能同时命中。
 */
export function matchesSkillSearch(skill: SkillSearchFields, query: string): boolean {
  const q = query.toLowerCase();
  return [skill.name, skill.description, skillFolderName(skill.storage_path), ...skill.tags].some((field) =>
    field.toLowerCase().includes(q),
  );
}
