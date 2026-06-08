/**
 * SpriteEngine — Canvas 2D spritesheet renderer for Codex-standard pet assets.
 *
 * [INPUT]
 * - None (standalone, no external module dependencies)
 *
 * [OUTPUT]
 * - SpriteEngine: Canvas 2D renderer with rAF animation loop, row/frame clamping
 * - SpritesheetMeta, CODEX_STANDARD: Spritesheet layout config and preset
 * - SpriteLoadState: Load lifecycle state type
 *
 * [POS]
 * Low-level Canvas 2D rendering engine for Codex-standard 8×N spritesheet assets.
 * Drives animation via requestAnimationFrame, auto-detects grid from image dimensions,
 * and falls back gracefully on missing rows/frames.
 */

export interface SpritesheetMeta {
  cols: number;
  rows: number;
  cellWidth: number;
  cellHeight: number;
  fps: number;
}

export const CODEX_STANDARD: SpritesheetMeta = {
  cols: 8,
  rows: 9,
  cellWidth: 192,
  cellHeight: 208,
  fps: 6,
};

export type SpriteLoadState = 'idle' | 'loading' | 'ready' | 'error';

export interface SpriteEngineOptions {
  canvas: HTMLCanvasElement;
  meta?: SpritesheetMeta;
  onLoadStateChange?: (state: SpriteLoadState) => void;
}

export class SpriteEngine {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D | null;
  private image: HTMLImageElement | null = null;
  private meta: SpritesheetMeta;
  private onLoadStateChange?: (state: SpriteLoadState) => void;

  private currentRow = 0;
  private currentFrame = 0;
  private effectiveCols = 0;
  private effectiveRows = 0;
  private animFrameId: number | null = null;
  private lastFrameTime = 0;
  private loadState: SpriteLoadState = 'idle';
  private destroyed = false;

  constructor(options: SpriteEngineOptions) {
    this.canvas = options.canvas;
    this.ctx = options.canvas.getContext('2d', { alpha: true });
    this.meta = options.meta ?? { ...CODEX_STANDARD };
    this.onLoadStateChange = options.onLoadStateChange;

    if (this.ctx) {
      this.ctx.imageSmoothingEnabled = false;
    }
  }

  private setLoadState(state: SpriteLoadState) {
    if (this.loadState === state) return;
    this.loadState = state;
    this.onLoadStateChange?.(state);
  }

  /**
   * Load a spritesheet image from URL. Auto-detects actual grid dimensions
   * from the image's natural size vs configured cell size.
   */
  loadSheet(url: string): Promise<void> {
    this.setLoadState('loading');

    return new Promise((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';

      img.onload = () => {
        if (this.destroyed) return;
        this.image = img;

        this.effectiveCols = Math.floor(img.naturalWidth / this.meta.cellWidth);
        this.effectiveRows = Math.floor(img.naturalHeight / this.meta.cellHeight);

        if (this.effectiveCols < 1 || this.effectiveRows < 1) {
          this.setLoadState('error');
          reject(new Error(`Spritesheet too small: ${img.naturalWidth}x${img.naturalHeight}`));
          return;
        }

        this.canvas.width = this.meta.cellWidth;
        this.canvas.height = this.meta.cellHeight;
        if (this.ctx) {
          this.ctx.imageSmoothingEnabled = false;
        }

        this.setLoadState('ready');
        this.renderFrame();
        resolve();
      };

      img.onerror = () => {
        if (this.destroyed) return;
        this.setLoadState('error');
        reject(new Error(`Failed to load spritesheet: ${url}`));
      };

      img.src = url;
    });
  }

  /** Set which animation row to play. Rows are 0-indexed. */
  setRow(row: number) {
    const safeRow = this.clampRow(row);
    if (safeRow === this.currentRow) return;
    this.currentRow = safeRow;
    this.currentFrame = 0;
    this.renderFrame();
  }

  getRow(): number {
    return this.currentRow;
  }

  /** Start the animation loop. */
  play() {
    if (this.animFrameId !== null) return;
    this.lastFrameTime = performance.now();
    this.tick(this.lastFrameTime);
  }

  /** Stop the animation loop (freezes on current frame). */
  stop() {
    if (this.animFrameId !== null) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
  }

  /** Update FPS without reloading the sheet. */
  setFps(fps: number) {
    this.meta.fps = Math.max(1, fps);
  }

  /** Update cell meta (e.g., for non-standard sheets). */
  setMeta(meta: Partial<SpritesheetMeta>) {
    Object.assign(this.meta, meta);
    if (this.image) {
      this.effectiveCols = Math.floor(this.image.naturalWidth / this.meta.cellWidth);
      this.effectiveRows = Math.floor(this.image.naturalHeight / this.meta.cellHeight);
    }
  }

  /** Clean up resources. */
  destroy() {
    this.destroyed = true;
    this.stop();
    this.image = null;
    this.ctx = null;
  }

  getLoadState(): SpriteLoadState {
    return this.loadState;
  }

  getEffectiveDimensions() {
    return { cols: this.effectiveCols, rows: this.effectiveRows };
  }

  private clampRow(row: number): number {
    if (this.effectiveRows === 0) return 0;
    if (row < 0) return 0;
    if (row >= this.effectiveRows) return 0; // fallback to idle (row 0)
    return row;
  }

  private clampFrame(frame: number): number {
    if (this.effectiveCols === 0) return 0;
    return frame % this.effectiveCols;
  }

  private renderFrame() {
    if (!this.ctx || !this.image || this.loadState !== 'ready') return;

    const { cellWidth, cellHeight } = this.meta;
    const col = this.clampFrame(this.currentFrame);
    const row = this.currentRow;

    const sx = col * cellWidth;
    const sy = row * cellHeight;

    this.ctx.clearRect(0, 0, cellWidth, cellHeight);
    this.ctx.drawImage(this.image, sx, sy, cellWidth, cellHeight, 0, 0, cellWidth, cellHeight);
  }

  private tick = (now: number) => {
    if (this.destroyed) return;

    const interval = 1000 / this.meta.fps;
    const delta = now - this.lastFrameTime;

    if (delta >= interval) {
      this.lastFrameTime = now - (delta % interval);
      this.currentFrame = this.clampFrame(this.currentFrame + 1);
      this.renderFrame();
    }

    this.animFrameId = requestAnimationFrame(this.tick);
  };
}
