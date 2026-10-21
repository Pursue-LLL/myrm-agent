/**
 * Persisted pet surface mode and bounds (localStorage).
 */

import type { PetSurfaceBounds, PetSurfaceMode } from './petSurfaceTypes';

const MODE_KEY = 'myrm-pet-surface-mode.v1';
const BOUNDS_KEY = 'myrm-pet-surface-bounds.v1';

export function loadPetSurfaceMode(): PetSurfaceMode {
  try {
    const raw = localStorage.getItem(MODE_KEY);
    if (raw === 'popped-out') {
      return 'popped-out';
    }
  } catch {
    /* ignore */
  }
  return 'embedded';
}

export function storePetSurfaceMode(mode: PetSurfaceMode): void {
  try {
    localStorage.setItem(MODE_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function loadPetSurfaceBounds(fallbackWidth: number, fallbackHeight: number): PetSurfaceBounds {
  try {
    const raw = localStorage.getItem(BOUNDS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<PetSurfaceBounds>;
      if (
        typeof parsed.x === 'number' &&
        typeof parsed.y === 'number' &&
        typeof parsed.width === 'number' &&
        typeof parsed.height === 'number'
      ) {
        return {
          x: parsed.x,
          y: parsed.y,
          width: parsed.width,
          height: parsed.height,
        };
      }
    }
  } catch {
    /* ignore */
  }
  const width = fallbackWidth;
  const height = fallbackHeight + 48;
  return {
    x: Math.max(24, window.innerWidth - width - 24),
    y: Math.max(24, window.innerHeight - height - 120),
    width,
    height,
  };
}

export function storePetSurfaceBounds(bounds: PetSurfaceBounds): void {
  try {
    localStorage.setItem(BOUNDS_KEY, JSON.stringify(bounds));
  } catch {
    /* ignore */
  }
}
