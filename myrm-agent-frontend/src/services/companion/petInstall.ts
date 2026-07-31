/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 前端 API 接入层)
 *
 * [OUTPUT]
 * - listInstalledCompanionPets: GET /companion/pets for Volume-installed pets
 * - installCompanionPet: POST /companion/pets/install for a Petdex slug
 * - uninstallCompanionPet: DELETE /companion/pets/{slug}
 *
 * [POS]
 * Shared Petdex install client used by PetGallery and /pet slash command.
 */

import { apiRequest } from '@/lib/api';

export interface InstalledCompanionPet {
  slug: string;
  display_name: string;
  content_sha256: string;
}

interface InstalledCompanionPetListResponse {
  pets: InstalledCompanionPet[];
}

export async function listInstalledCompanionPets(): Promise<InstalledCompanionPet[]> {
  const data = await apiRequest<InstalledCompanionPetListResponse>('/companion/pets');
  return Array.isArray(data.pets) ? data.pets : [];
}

export async function installCompanionPet(slug: string): Promise<InstalledCompanionPet> {
  return apiRequest<InstalledCompanionPet>('/companion/pets/install', {
    method: 'POST',
    body: JSON.stringify({ slug: slug.trim() }),
  });
}

interface UninstallCompanionPetResponse {
  removed: boolean;
}

export async function uninstallCompanionPet(slug: string): Promise<void> {
  const normalized = slug.trim();
  await apiRequest<UninstallCompanionPetResponse>(
    `/companion/pets/${encodeURIComponent(normalized)}`,
    { method: 'DELETE' },
  );
}
