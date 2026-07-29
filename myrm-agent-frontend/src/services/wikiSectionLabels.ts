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
