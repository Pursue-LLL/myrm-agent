/**
 * [INPUT]
 * - @/lib/api::apiRequest, ApiError (POS: 前端 API 接入层)
 *
 * [OUTPUT]
 * - listInstalledCompanionPets: GET /companion/pets for Volume-installed pets
 * - installCompanionPet: POST /companion/pets/install for a Petdex slug
 * - uninstallCompanionPet: DELETE /companion/pets/{slug}
 * - CompanionFeatureDisabledError: companion_mode feature gate blocked install
 *
 * [POS]
 * Shared Petdex install client used by PetGallery and /pet slash command.
 */

import { ApiError, apiRequest } from '@/lib/api';

export interface InstalledCompanionPet {
  slug: string;
  display_name: string;
  content_sha256: string;
  format_label?: string | null;
  format_tier?: string | null;
}

interface InstalledCompanionPetListResponse {
  pets: InstalledCompanionPet[];
}

export class CompanionFeatureDisabledError extends Error {
  readonly code = 'COMPANION_FEATURE_DISABLED';

  constructor() {
    super('COMPANION_FEATURE_DISABLED');
    this.name = 'CompanionFeatureDisabledError';
  }
}

export async function listInstalledCompanionPets(): Promise<InstalledCompanionPet[]> {
  const data = await apiRequest<InstalledCompanionPetListResponse>('/companion/pets', {
    silent: true,
  });
  return Array.isArray(data.pets) ? data.pets : [];
}

export async function installCompanionPet(slug: string): Promise<InstalledCompanionPet> {
  try {
    return await apiRequest<InstalledCompanionPet>('/companion/pets/install', {
      method: 'POST',
      body: JSON.stringify({ slug: slug.trim() }),
      silent: true,
    });
  } catch (err) {
    if (err instanceof ApiError && err.code === 403) {
      throw new CompanionFeatureDisabledError();
    }
    throw err;
  }
}

interface UninstallCompanionPetResponse {
  removed: boolean;
}

export async function uninstallCompanionPet(slug: string): Promise<void> {
  const normalized = slug.trim();
  await apiRequest<UninstallCompanionPetResponse>(`/companion/pets/${encodeURIComponent(normalized)}`, {
    method: 'DELETE',
    silent: true,
  });
}
