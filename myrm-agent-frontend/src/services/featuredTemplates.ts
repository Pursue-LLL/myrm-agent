/**
 * Featured expert templates for the empty-chat suggestion strip.
 *
 * [INPUT] services/agentTemplates::getTemplates (POS: template list API)
 * [OUTPUT] peekFeaturedTemplates, loadFeaturedTemplates, invalidateFeaturedTemplates
 * [POS] The strip remounts on every new chat. A short cache plus one shared in-flight request keeps the template
 * request off the first-screen path, and a cached answer lets the strip render without a loading placeholder.
 */

import { getTemplates, type TemplateListItem } from '@/services/agentTemplates';

const FEATURED_LIMIT = 4;
const FEATURED_CACHE_TTL_MS = 60_000;

let cache: { templates: TemplateListItem[]; cachedAt: number } | null = null;
let inFlight: Promise<TemplateListItem[]> | null = null;
// Bumped by invalidation so a request that was already running cannot refill the cache afterwards.
let generation = 0;

/** The cached featured templates while they are fresh, otherwise null. */
export function peekFeaturedTemplates(now: number = Date.now()): TemplateListItem[] | null {
  return cache && now - cache.cachedAt < FEATURED_CACHE_TTL_MS ? cache.templates : null;
}

/** Featured teams and Pareto presets, at most four. A failed request is not cached, so the next mount retries. */
export function loadFeaturedTemplates(): Promise<TemplateListItem[]> {
  const fresh = peekFeaturedTemplates();
  if (fresh) {
    return Promise.resolve(fresh);
  }
  const requestGeneration = generation;
  inFlight ??= getTemplates()
    .then((templates) => {
      const featured = templates
        .filter((template) => template.agent_type === 'team' || template.is_pareto_preset)
        .slice(0, FEATURED_LIMIT);
      if (requestGeneration === generation) {
        cache = { templates: featured, cachedAt: Date.now() };
      }
      return featured;
    })
    .finally(() => {
      if (requestGeneration === generation) {
        inFlight = null;
      }
    });
  return inFlight;
}

export function invalidateFeaturedTemplates(): void {
  generation += 1;
  cache = null;
  inFlight = null;
}
