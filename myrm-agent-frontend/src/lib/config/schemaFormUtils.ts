export interface SchemaPropertyLike {
  title?: string;
  description?: string;
  type?: string;
  default?: unknown;
  enum?: string[];
  'ui:widget'?: string;
  'x-ui-section'?: string;
  'x-ui-group'?: string;
  'x-ui-visible-if'?: string;
  'x-ui-requires-field'?: string;
  anyOf?: Record<string, unknown>[];
}

export const TITLE_KEY_ALIASES: Record<string, string[]> = {
  enableWebNotifications: ['webNotifications'],
  enableCompletionSound: ['completionSound'],
};

export const DESC_KEY_ALIASES: Record<string, string[]> = {
  enableWebNotifications: ['webNotificationsDesc'],
  enableCompletionSound: ['completionSoundDesc'],
  timezone: ['timezoneDescription'],
};

export function isMissingTranslation(value: string, namespace: string, key: string): boolean {
  return !value || value === `${namespace}.${key}`;
}

export function getSchemaUiSection(prop: SchemaPropertyLike): string | undefined {
  const section = prop['x-ui-section'];
  return typeof section === 'string' ? section : undefined;
}

export function matchesSchemaSection(prop: SchemaPropertyLike, section?: string): boolean {
  if (!section) return true;
  return getSchemaUiSection(prop) === section;
}

export function getSchemaUiGroup(prop: SchemaPropertyLike): string {
  const group = prop['x-ui-group'];
  return typeof group === 'string' ? group : 'basic';
}

export function matchesSchemaGroup(prop: SchemaPropertyLike, group?: string): boolean {
  if (!group) return true;
  return getSchemaUiGroup(prop) === group;
}

export function matchesSchemaFilters(prop: SchemaPropertyLike, filters: { section?: string; group?: string }): boolean {
  return matchesSchemaSection(prop, filters.section) && matchesSchemaGroup(prop, filters.group);
}

export interface SchemaVisibilityContext {
  isLocal: boolean;
  value: Record<string, unknown>;
}

export function matchesSchemaVisibility(prop: SchemaPropertyLike, context?: SchemaVisibilityContext): boolean {
  if (!context) return true;

  const visibleIf = prop['x-ui-visible-if'];
  if (visibleIf === 'local' && !context.isLocal) {
    return false;
  }

  const requiresField = prop['x-ui-requires-field'];
  if (requiresField && !context.value[requiresField]) {
    return false;
  }

  return true;
}

export function supportsSchemaControl(type: string | undefined, isEnum: boolean): boolean {
  return type === 'boolean' || (type === 'string' && !isEnum) || isEnum;
}

export function resolveSchemaPropertyType(prop: SchemaPropertyLike): {
  type: string | undefined;
  isEnum: boolean;
  enumValues: string[] | undefined;
} {
  let type = prop.type;
  let isEnum = !!prop.enum;
  let enumValues = prop.enum;

  if (!type && prop.anyOf) {
    const nonNullType = prop.anyOf.find((item) => item.type !== 'null');
    if (nonNullType) {
      type = nonNullType.type as string;
      if (nonNullType.enum) {
        isEnum = true;
        enumValues = nonNullType.enum as string[];
      }
    }
  }

  return { type, isEnum, enumValues };
}

export function resolveFieldLabels(
  translate: (key: string) => string,
  hasKey: (key: string) => boolean,
  namespace: string,
  key: string,
  prop: SchemaPropertyLike,
  locale: string,
): { title: string; desc: string } {
  const titleCandidates = [key, ...(TITLE_KEY_ALIASES[key] ?? [])];
  let displayTitle = '';
  for (const candidate of titleCandidates) {
    if (hasKey(candidate)) {
      const translated = translate(candidate);
      if (!isMissingTranslation(translated, namespace, candidate)) {
        displayTitle = translated;
        break;
      }
    }
  }
  if (!displayTitle) {
    const isChineseLocale = locale.startsWith('zh');
    displayTitle = isChineseLocale && prop.description?.trim() ? prop.description.trim() : key;
  }

  const descCandidates = [`${key}Desc`, ...(DESC_KEY_ALIASES[key] ?? [])];
  let displayDesc = '';
  for (const candidate of descCandidates) {
    if (hasKey(candidate)) {
      const translated = translate(candidate);
      if (!isMissingTranslation(translated, namespace, candidate)) {
        displayDesc = translated;
        break;
      }
    }
  }

  if (displayDesc && displayDesc === displayTitle) {
    displayDesc = '';
  }

  return { title: displayTitle, desc: displayDesc };
}

export function resolveEnumLabel(
  translate: (key: string) => string,
  hasKey: (key: string) => boolean,
  namespace: string,
  fieldKey: string,
  enumValue: string,
): string {
  if (fieldKey === 'webTtsProvider') {
    const normalized = enumValue === 'fish_audio' ? 'fishAudio' : enumValue;
    const webTtsKey = `webTts.${normalized}`;
    if (hasKey(webTtsKey)) {
      const label = translate(webTtsKey);
      if (!isMissingTranslation(label, namespace, webTtsKey)) {
        return label;
      }
    }
  }

  const optionKey = `${fieldKey}Options.${enumValue}`;
  if (hasKey(optionKey)) {
    const label = translate(optionKey);
    if (!isMissingTranslation(label, namespace, optionKey)) {
      return label;
    }
  }

  return enumValue;
}
