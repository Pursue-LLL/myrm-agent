/**
 * [INPUT]
 * (none)
 *
 * [OUTPUT]
 * - PET_SIZES / PetSize / PetPosition types
 * - getStoredPosition / storePosition / getStoredSize / storeSize
 * - clampPosition / defaultPosition
 *
 * [POS]
 * localStorage helpers for embedded pet overlay position and display size.
 */

export const PET_SIZES = [48, 64, 80, 96, 128] as const;
export type PetSize = (typeof PET_SIZES)[number];

export interface PetPosition {
  x: number;
  y: number;
}

export function getStoredPosition(): PetPosition {
  try {
    const raw = localStorage.getItem('myrm-pet-position');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (typeof parsed.x === 'number' && typeof parsed.y === 'number') {
        return parsed;
      }
    }
  } catch {}
  return { x: -1, y: -1 };
}

export function storePosition(pos: PetPosition): void {
  try {
    localStorage.setItem('myrm-pet-position', JSON.stringify(pos));
  } catch {}
}

export function getStoredSize(): PetSize {
  try {
    const raw = localStorage.getItem('myrm-pet-size');
    if (raw) {
      const n = Number(raw);
      if (PET_SIZES.includes(n as PetSize)) {return n as PetSize;}
    }
  } catch {}
  return 64;
}

export function storeSize(size: PetSize): void {
  try {
    localStorage.setItem('myrm-pet-size', String(size));
  } catch {}
}

export function clampPosition(pos: PetPosition, size: number): PetPosition {
  const maxX = Math.max(0, window.innerWidth - size);
  const maxY = Math.max(0, window.innerHeight - size);
  return {
    x: Math.max(0, Math.min(pos.x, maxX)),
    y: Math.max(0, Math.min(pos.y, maxY)),
  };
}

export function defaultPosition(size: number): PetPosition {
  return {
    x: window.innerWidth - size - 24,
    y: window.innerHeight - size - 120,
  };
}
