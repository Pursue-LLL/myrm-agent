/**
 * [INPUT]
 * 无外部依赖（纯函数）
 *
 * [OUTPUT]
 * resolveWikiSectionLabel: Wiki 区块标题 → i18n key 解析。
 * wikiSectionLabeler: 绑定翻译器后的区块标题译名函数（来源命名函数的 sectionLabel 参数）。
 *
 * [POS]
 * Wiki 区块标题 i18n key 映射纯函数（Chat/设置共享）。
 */

const WIKI_SECTION_I18N_KEYS: Record<string, string> = {
  index_routing: 'kb_section_index_routing',
};

export function resolveWikiSectionLabel(
  section: string | undefined,
  translate: (key: string) => string,
): string | undefined {
  if (!section) {
    return undefined;
  }
  const key = WIKI_SECTION_I18N_KEYS[section];
  if (key) {
    return translate(key);
  }
  return section;
}

/** 区块标题的译名函数：已知区块译成界面语言，其余原样返回。 */
export function wikiSectionLabeler(translate: (key: string) => string): (section: string) => string {
  return (section) => resolveWikiSectionLabel(section, translate) ?? section;
}
