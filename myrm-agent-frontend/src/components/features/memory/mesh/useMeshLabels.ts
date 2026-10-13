'use client';

/**
 * [INPUT]
 * next-intl::useTranslations (memory.mesh.domains, memory.mesh.categories, memory.types)
 *
 * [OUTPUT]
 * useMeshLabels: Localized names for the domain, category and memory-type identifiers the mesh API returns.
 *
 * [POS]
 * Presentation helper shared by the domain cards and the drill-down dialog, so raw API identifiers
 * never reach the screen.
 */

import { useTranslations } from 'next-intl';

export interface MeshLabels {
  domain: (id: string) => string;
  category: (id: string) => string;
  memoryType: (id: string) => string;
}

/**
 * An identifier this build has no name for (for example a category carried in by an imported bundle)
 * is the user's own data rather than a diagnostic, so it is shown as-is.
 */
export function useMeshLabels(): MeshLabels {
  const tDomains = useTranslations('memory.mesh.domains');
  const tCategories = useTranslations('memory.mesh.categories');
  const tTypes = useTranslations('memory.types');

  return {
    domain: (id) => {
      const key = `${id}.title` as Parameters<typeof tDomains>[0];
      return tDomains.has(key) ? tDomains(key) : id;
    },
    category: (id) => {
      const key = id as Parameters<typeof tCategories>[0];
      return tCategories.has(key) ? tCategories(key) : id;
    },
    memoryType: (id) => {
      const key = id as Parameters<typeof tTypes>[0];
      return tTypes.has(key) ? tTypes(key) : id;
    },
  };
}
