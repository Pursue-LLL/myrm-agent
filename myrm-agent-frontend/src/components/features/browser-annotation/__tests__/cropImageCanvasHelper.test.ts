import { describe, it, expect } from 'vitest';
import { cropImageFromBase64 } from '../cropImageCanvasHelper';
import type { PinBoundingBox } from '../browserAnnotationTypes';

describe('cropImageCanvasHelper', () => {
  it('gracefully handles empty or zero-dimension box', async () => {
    const rawBase64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
    const box: PinBoundingBox = {
      x: 0,
      y: 0,
      width: 0,
      height: 0,
      viewportWidth: 0,
      viewportHeight: 0,
    };

    const result = await cropImageFromBase64(rawBase64, box);
    expect(result).toBeDefined();
  });

  it('handles valid data URL without crashing in jsdom', async () => {
    const rawDataUrl = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
    const box: PinBoundingBox = {
      x: 10,
      y: 10,
      width: 100,
      height: 50,
      viewportWidth: 800,
      viewportHeight: 600,
    };

    const result = await cropImageFromBase64(rawDataUrl, box);
    expect(result).toBeDefined();
  });
});
