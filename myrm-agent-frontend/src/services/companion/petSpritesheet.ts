/**
 * [INPUT]
 * - @/lib/api::getApiUrl (POS: 前端 API 接入层)
 *
 * [OUTPUT]
 * - CompanionSpriteConfig: persisted sprite selection shape
 * - companionPetSpritesheetUrl: local serve URL for an installed pet slug
 * - resolveCompanionSpritesheetUrl: map store config to serve URL
 *
 * [POS]
 * Companion Petdex sprite URL resolver. Maps pet_slug config to the server-local
 * spritesheet endpoint; never returns remote petdex CDN URLs.
 */

import { getApiUrl } from '@/lib/api';

export interface CompanionSpriteConfig {
  petSlug: string;
  displayName?: string;
  contentSha256?: string;
}

export function companionPetSpritesheetUrl(petSlug: string): string {
  return getApiUrl(`/companion/pets/${encodeURIComponent(petSlug)}/spritesheet`);
}

export function resolveCompanionSpritesheetUrl(config: CompanionSpriteConfig | null | undefined): string | null {
  if (!config?.petSlug) {
    return null;
  }
  return companionPetSpritesheetUrl(config.petSlug);
}
