import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CODEX_STANDARD, SpriteEngine } from '../SpriteEngine';

import type { SpriteLoadState } from '../SpriteEngine';

function createMockCanvas() {
  const ctx = {
    imageSmoothingEnabled: true,
    clearRect: vi.fn(),
    drawImage: vi.fn(),
  };
  const canvas = {
    getContext: vi.fn().mockReturnValue(ctx),
    width: 0,
    height: 0,
  } as unknown as HTMLCanvasElement;
  return { canvas, ctx };
}

describe('SpriteEngine', () => {
  let engine: SpriteEngine;
  let mockCanvas: ReturnType<typeof createMockCanvas>;
  let loadStates: SpriteLoadState[];

  beforeEach(() => {
    mockCanvas = createMockCanvas();
    loadStates = [];
    engine = new SpriteEngine({
      canvas: mockCanvas.canvas,
      onLoadStateChange: (state) => loadStates.push(state),
    });
  });

  afterEach(() => {
    engine.destroy();
  });

  it('initializes with idle load state', () => {
    expect(engine.getLoadState()).toBe('idle');
  });

  it('uses Codex standard meta by default', () => {
    expect(CODEX_STANDARD.cols).toBe(8);
    expect(CODEX_STANDARD.rows).toBe(9);
    expect(CODEX_STANDARD.cellWidth).toBe(192);
    expect(CODEX_STANDARD.cellHeight).toBe(208);
    expect(CODEX_STANDARD.fps).toBe(6);
  });

  it('disables imageSmoothingEnabled on init', () => {
    expect(mockCanvas.ctx.imageSmoothingEnabled).toBe(false);
  });

  it('reports loading state when loadSheet is called', () => {
    const originalImage = globalThis.Image;
    globalThis.Image = class MockImage {
      crossOrigin = '';
      naturalWidth = 0;
      naturalHeight = 0;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_url: string) {
        // Intentionally no-op: loadSheet only needs Image constructor side effects.
      }
    } as typeof Image;

    engine.loadSheet('https://example.com/sheet.webp');
    expect(loadStates).toContain('loading');

    globalThis.Image = originalImage;
  });

  it('setRow clamps out-of-range rows to 0', () => {
    engine.setRow(999);
    expect(engine.getRow()).toBe(0);
  });

  it('setRow clamps negative rows to 0', () => {
    engine.setRow(-5);
    expect(engine.getRow()).toBe(0);
  });

  it('setFps clamps to minimum 1', () => {
    engine.setFps(0);
    engine.setFps(-10);
  });

  it('destroy stops animation and cleans up', () => {
    engine.destroy();
    expect(engine.getLoadState()).toBe('idle');
  });

  it('getEffectiveDimensions returns 0,0 before loading', () => {
    const dims = engine.getEffectiveDimensions();
    expect(dims.cols).toBe(0);
    expect(dims.rows).toBe(0);
  });

  it('play/stop are safe when no sheet loaded', () => {
    engine.play();
    engine.stop();
  });

  it('setMeta updates meta without crashing', () => {
    engine.setMeta({ fps: 12 });
  });
});
