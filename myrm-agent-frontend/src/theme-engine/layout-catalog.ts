import type { ThemeLayoutId } from './schema';

export interface ThemeLayoutCatalogItem {
  id: ThemeLayoutId;
  nameKey: string;
  descriptionKey: string;
  guidanceKey: string;
}

export const THEME_LAYOUT_CATALOG: readonly ThemeLayoutCatalogItem[] = [
  {
    id: 'full-bleed',
    nameKey: 'fullBleed.name',
    descriptionKey: 'fullBleed.description',
    guidanceKey: 'fullBleed.guidance',
  },
  {
    id: 'nav-rail-focus',
    nameKey: 'navRailFocus.name',
    descriptionKey: 'navRailFocus.description',
    guidanceKey: 'navRailFocus.guidance',
  },
  {
    id: 'chat-hero',
    nameKey: 'chatHero.name',
    descriptionKey: 'chatHero.description',
    guidanceKey: 'chatHero.guidance',
  },
  {
    id: 'work-dense',
    nameKey: 'workDense.name',
    descriptionKey: 'workDense.description',
    guidanceKey: 'workDense.guidance',
  },
] as const;

export function getLayoutCatalogItem(layoutId: ThemeLayoutId): ThemeLayoutCatalogItem {
  const item = THEME_LAYOUT_CATALOG.find((entry) => entry.id === layoutId);
  if (!item) {
    return THEME_LAYOUT_CATALOG[0];
  }
  return item;
}
