import { recommendLayoutFromAspect } from './recommend-layout-from-aspect';
import type { ThemeLayoutId } from './schema';

/**
 * [INPUT]
 * - Browser Canvas / ImageBitmap (client-only)
 *
 * [OUTPUT]
 * - sampleHeroImageData, sampleHeroImageBlob, HeroImageSample
 *
 * [POS]
 * Deterministic hero media sampling for Theme Studio palette/layout suggestions (no LLM).
 */

const MAX_SAMPLE_EDGE = 64;
const MIN_ALPHA = 128;

export interface HeroImageSample {
  primaryHex: string;
  focalX: number;
  focalY: number;
  aspectRatio: number;
  recommendedLayoutId: ThemeLayoutId;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function rgbToHex(r: number, g: number, b: number): string {
  const toByte = (channel: number) =>
    Math.max(0, Math.min(255, Math.round(channel)))
      .toString(16)
      .padStart(2, '0');
  return `#${toByte(r)}${toByte(g)}${toByte(b)}`;
}

function isNeutral(r: number, g: number, b: number): boolean {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  if (max - min < 18) {
    return true;
  }
  if (max > 245 && min > 210) {
    return true;
  }
  if (max < 24) {
    return true;
  }
  return false;
}

function hueBucket(r: number, g: number, b: number): number {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const delta = max - min;
  if (delta < 0.04) {
    return -1;
  }
  let hue = 0;
  if (max === rn) {
    hue = ((gn - bn) / delta) % 6;
  } else if (max === gn) {
    hue = (bn - rn) / delta + 2;
  } else {
    hue = (rn - gn) / delta + 4;
  }
  hue *= 60;
  if (hue < 0) {
    hue += 360;
  }
  return Math.floor(hue / 10);
}

/** Pure sampling from ImageData — unit-testable without browser file I/O. */
export function sampleHeroImageData(imageData: ImageData): HeroImageSample {
  const { width, height, data } = imageData;
  const aspectRatio = width / height;

  const bucketSums = new Map<number, { r: number; g: number; b: number; count: number }>();
  let focalX = 0;
  let focalY = 0;
  let focalWeight = 0;
  let fallbackR = 0;
  let fallbackG = 0;
  let fallbackB = 0;
  let fallbackCount = 0;

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * 4;
      const alpha = data[index + 3];
      if (alpha < MIN_ALPHA) {
        continue;
      }
      const r = data[index];
      const g = data[index + 1];
      const b = data[index + 2];

      fallbackR += r;
      fallbackG += g;
      fallbackB += b;
      fallbackCount += 1;

      if (isNeutral(r, g, b)) {
        continue;
      }

      const bucket = hueBucket(r, g, b);
      if (bucket < 0) {
        continue;
      }

      const entry = bucketSums.get(bucket) ?? { r: 0, g: 0, b: 0, count: 0 };
      entry.r += r;
      entry.g += g;
      entry.b += b;
      entry.count += 1;
      bucketSums.set(bucket, entry);

      const chroma = Math.max(r, g, b) - Math.min(r, g, b);
      const weight = chroma + 8;
      focalX += x * weight;
      focalY += y * weight;
      focalWeight += weight;
    }
  }

  let primaryHex = '#588e95';
  if (bucketSums.size > 0) {
    const winner = [...bucketSums.values()].sort((a, b) => b.count - a.count)[0];
    primaryHex = rgbToHex(winner.r / winner.count, winner.g / winner.count, winner.b / winner.count);
  } else if (fallbackCount > 0) {
    primaryHex = rgbToHex(fallbackR / fallbackCount, fallbackG / fallbackCount, fallbackB / fallbackCount);
  }

  return {
    primaryHex,
    focalX: clamp01(focalWeight > 0 ? focalX / focalWeight / width : 0.5),
    focalY: clamp01(focalWeight > 0 ? focalY / focalWeight / height : 0.5),
    aspectRatio,
    recommendedLayoutId: recommendLayoutFromAspect(aspectRatio),
  };
}

async function loadImageDataFromBlob(blob: Blob): Promise<ImageData> {
  if (typeof document === 'undefined') {
    throw new Error('Hero image sampling requires a browser environment');
  }
  const bitmap = await createImageBitmap(blob);
  const scale = MAX_SAMPLE_EDGE / Math.max(bitmap.width, bitmap.height);
  const width = Math.max(1, Math.round(bitmap.width * Math.min(1, scale)));
  const height = Math.max(1, Math.round(bitmap.height * Math.min(1, scale)));
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d');
  if (!context) {
    bitmap.close();
    throw new Error('Canvas context unavailable for hero sampling');
  }
  context.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  const imageData = context.getImageData(0, 0, width, height);
  return imageData;
}

export async function sampleHeroImageBlob(blob: Blob): Promise<HeroImageSample> {
  const imageData = await loadImageDataFromBlob(blob);
  return sampleHeroImageData(imageData);
}
