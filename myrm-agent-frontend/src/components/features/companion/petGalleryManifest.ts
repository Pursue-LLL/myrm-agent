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
  if (!resp.ok) throw new Error(`Manifest fetch failed: ${resp.status}`);

  const payload = await resp.json();
  const raw = payload?.pets;
  if (!Array.isArray(raw)) throw new Error('Invalid manifest format');

  const pets: ManifestPet[] = [];
  for (const entry of raw) {
    if (!entry?.slug || !entry?.spritesheetUrl) continue;
    pets.push({
      slug: String(entry.slug),
      displayName: String(entry.displayName || entry.slug),
      kind: String(entry.kind || 'pet'),
      spritesheetUrl: String(entry.spritesheetUrl),
    });
  }

  const cacheObj = { ts: Date.now(), pets };
  memoryCache = cacheObj;
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(cacheObj));
  } catch {}

  return pets;
}
