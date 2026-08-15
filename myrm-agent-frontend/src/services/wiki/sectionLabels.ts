/**
 * [INPUT]
 * 无外部依赖（纯函数）
 *
 * [OUTPUT]
 * resolveWikiSectionLabel: Wiki 区块标题 → i18n key 解析。
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
