import { describe, expect, it } from 'vitest';
import { sampleHeroImageData } from '../sample-hero-image';

if (typeof ImageData === 'undefined') {
  globalThis.ImageData = class ImageDataPolyfill {
    readonly data: Uint8ClampedArray;
    readonly width: number;
    readonly height: number;
    constructor(data: Uint8ClampedArray, width: number, height: number) {
      this.data = data;
      this.width = width;
      this.height = height;
    }
  } as unknown as typeof ImageData;
}

function solidImageData(width: number, height: number, r: number, g: number, b: number): ImageData {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let index = 0; index < data.length; index += 4) {
    data[index] = r;
    data[index + 1] = g;
    data[index + 2] = b;
    data[index + 3] = 255;
  }
  return new ImageData(data, width, height);
}

describe('sampleHeroImageData', () => {
  it('derives palette hex from saturated pixels', () => {
    const sample = sampleHeroImageData(solidImageData(32, 32, 30, 120, 200));
    expect(sample.primaryHex.toLowerCase()).toBe('#1e78c8');
    expect(sample.focalX).toBeGreaterThan(0.4);
    expect(sample.focalX).toBeLessThan(0.6);
  });

  it('recommends layout from aspect ratio', () => {
    const wide = sampleHeroImageData(solidImageData(64, 32, 200, 80, 80));
    expect(wide.recommendedLayoutId).toBe('full-bleed');
    expect(wide.aspectRatio).toBe(2);
  });
});
