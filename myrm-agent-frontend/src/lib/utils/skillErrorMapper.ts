/**
 * 技能相关错误信息映射
 *
 * 将后端返回的技术性错误信息映射为用户友好的翻译键
 */

// 后端错误关键词到翻译键的映射
const ERROR_MAPPINGS: Array<{
  pattern: RegExp;
  translationKey: string;
}> = [
  {
    pattern: /目录为空|directory.*empty|does not exist/i,
    translationKey: 'errors.directoryEmpty',
  },
  {
    pattern: /SKILL\.md.*缺失|missing.*SKILL\.md|缺少必需的 SKILL\.md/i,
    translationKey: 'errors.skillMdMissing',
  },
  {
    pattern: /名称格式无效|invalid.*name|name.*invalid/i,
    translationKey: 'errors.invalidSkillName',
  },
  {
    pattern: /文件过大|too large|exceeds.*limit/i,
    translationKey: 'errors.zipTooLarge',
  },
  {
    pattern: /network|fetch|connection|ECONNREFUSED|ENOTFOUND/i,
    translationKey: 'errors.networkError',
  },
];

/**
 * 将后端错误信息映射为翻译键
 *
 * @param errorMessage - 后端返回的原始错误信息
 * @returns 翻译键（如 'errors.skillMdMissing'），如果无法映射则返回 null
 *
 * @example
 * mapSkillError('缺少必需的 SKILL.md 文件')
 * // => 'errors.skillMdMissing'
 */
export function mapSkillErrorToTranslationKey(errorMessage: string): string | null {
  if (!errorMessage) {
    return null;
  }

  for (const { pattern, translationKey } of ERROR_MAPPINGS) {
    if (pattern.test(errorMessage)) {
      return translationKey;
    }
  }

  return null;
}

/**
 * 获取用户友好的错误描述
 *
 * @param errorMessage - 后端返回的原始错误信息
 * @param t - 翻译函数 (useTranslations 返回的函数)
 * @returns 用户友好的错误描述，如果无法映射则返回原始错误信息
 */
export function getFriendlyErrorMessage(errorMessage: string, t: (key: string) => string): string {
  const translationKey = mapSkillErrorToTranslationKey(errorMessage);

  if (translationKey) {
    // 尝试获取翻译，如果翻译不存在则返回原始错误
    const translated = t(translationKey);
    // next-intl 在找不到翻译时会返回键本身，所以检查是否相同
    if (translated !== translationKey) {
      return translated;
    }
  }

  // 如果无法映射，返回原始错误信息
  return errorMessage;
}
