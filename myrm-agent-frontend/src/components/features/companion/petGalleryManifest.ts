/**
 * petGalleryManifest — Petdex public manifest fetch with session cache.
 *
 * [INPUT]
 * - browser fetch API
 *
 * [OUTPUT]
 * - ManifestPet: normalized manifest entry
 * - fetchPetdexManifest: cached manifest loader
 *
 * [POS]
 * Best-effort catalog source for PetGallery; failures are handled by gallery fail-open UI.
 */

export interface ManifestPet {
  slug: string;
  displayName: string;
  kind: string;
  spritesheetUrl: string;
  curated: boolean;
}

const MANIFEST_URL = 'https://petdex.dev/api/manifest';
const CACHE_KEY = 'myrm-petdex-manifest';
const CACHE_TTL_MS = 300_000;

let memoryCache: { ts: number; pets: ManifestPet[] } | null = null;

export async function fetchPetdexManifest(): Promise<ManifestPet[]> {
  if (memoryCache && Date.now() - memoryCache.ts < CACHE_TTL_MS) {
    return memoryCache.pets;
  }

  try {
    const cached = sessionStorage.getItem(CACHE_KEY);
    if (cached) {
      const parsed = JSON.parse(cached) as { ts: number; pets: ManifestPet[] };
      if (Date.now() - parsed.ts < CACHE_TTL_MS) {
        memoryCache = parsed;
        return parsed.pets;
      }
    }
  } catch {}

  const resp = await fetch(MANIFEST_URL);
  if (!resp.ok) {throw new Error(`Manifest fetch failed: ${resp.status}`);}

  const payload = await resp.json();
  const raw = payload?.pets;
  if (!Array.isArray(raw)) {throw new Error('Invalid manifest format');}

  const pets: ManifestPet[] = [];
  for (const entry of raw) {
    if (!entry?.slug || !entry?.spritesheetUrl) {continue;}
    pets.push({
      slug: String(entry.slug),
      displayName: String(entry.displayName || entry.slug),
      kind: String(entry.kind || 'pet'),
      spritesheetUrl: String(entry.spritesheetUrl),
      curated: String(entry.spritesheetUrl).includes('/curated/'),
    });
  }

  const cacheObj = { ts: Date.now(), pets };
  memoryCache = cacheObj;
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(cacheObj));
  } catch {}

  return pets;
}

export function rankManifestPets(
  pets: ManifestPet[],
  options: { installedSlugs?: ReadonlySet<string>; activeSlug?: string } = {},
): ManifestPet[] {
  const installed = options.installedSlugs ?? new Set<string>();
  const activeSlug = options.activeSlug;
  const score = (pet: ManifestPet) =>
    (pet.curated ? 4 : 0) +
    (installed.has(pet.slug) ? 2 : 0) +
    (activeSlug === pet.slug ? 1 : 0);
  return [...pets].sort((a, b) => score(b) - score(a));
}

export function petdexPetPageUrl(slug: string): string {
  return `https://petdex.dev/pets/${encodeURIComponent(slug)}`;
}
