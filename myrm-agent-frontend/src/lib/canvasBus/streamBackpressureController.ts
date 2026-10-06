/**
 * [INPUT]
 * Stream tokens/chunks from LLM SSE or WebSocket channels
 *
 * [OUTPUT]
 * StreamBackpressureController: Adaptive RAF-throttled chunk buffer preventing UI frame drops
 * BackpressureConfig: Configuration for rendering frame budget and buffer depth
 * BackpressureMetrics: Telemetry on merged chunks, rendered frames, and emergency flushes
 *
 * [POS]
 * myrm-agent-frontend/src/lib/canvasBus/streamBackpressureController.ts
 * Stream rendering backpressure controller eliminating UI freezing at >150 tokens/s.
 */

export interface BackpressureConfig {
  readonly targetFps: number;
  readonly maxBufferedChars: number;
  readonly maxWaitMs: number;
}

export interface BackpressureMetrics {
  totalChunksPushed: number;
  totalFramesRendered: number;
  totalMergedChunks: number;
  emergencyFlushes: number;
}

export type StreamRenderCallback = (accumulatedChunk: string) => void;

const DEFAULT_CONFIG: BackpressureConfig = {
  targetFps: 60,
  maxBufferedChars: 800,
  maxWaitMs: 32,
};

export class StreamBackpressureController {
  private readonly config: BackpressureConfig;
  private readonly onRender: StreamRenderCallback;
  private buffer: string[] = [];
  private bufferedCharsCount = 0;
  private scheduledFrameId: number | null = null;
  private fallbackTimerId: ReturnType<typeof setTimeout> | null = null;
  private lastFlushTimestamp = 0;
  private isDestroyed = false;

  private readonly metrics: BackpressureMetrics = {
    totalChunksPushed: 0,
    totalFramesRendered: 0,
    totalMergedChunks: 0,
    emergencyFlushes: 0,
  };

  public constructor(onRender: StreamRenderCallback, config?: Partial<BackpressureConfig & { useTimerFallback?: boolean }>) {
    this.onRender = onRender;
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.lastFlushTimestamp = Date.now();
  }

  public pushChunk(chunk: string): void {
    if (this.isDestroyed || !chunk) {
      return;
    }

    this.metrics.totalChunksPushed += 1;
    this.buffer.push(chunk);
    this.bufferedCharsCount += chunk.length;

    // Emergency backpressure release: if buffer volume is too deep, flush immediately
    if (this.bufferedCharsCount >= this.config.maxBufferedChars) {
      this.metrics.emergencyFlushes += 1;
      this.flushSync();
      return;
    }

    this.scheduleFrame();
  }

  private scheduleFrame(): void {
    if (this.scheduledFrameId !== null || this.fallbackTimerId !== null) {
      return;
    }

    const frameIntervalMs = Math.floor(1000 / this.config.targetFps);
    const now = Date.now();
    const timeSinceLastFlush = now - this.lastFlushTimestamp;

    if (this.lastFlushTimestamp > 0 && timeSinceLastFlush >= this.config.maxWaitMs && this.buffer.length > 1) {
      // Exceeded max wait time with existing backlog, flush immediately to keep UI responsive
      this.flushSync();
      return;
    }

    if (
      typeof window !== 'undefined'
      && typeof window.requestAnimationFrame === 'function'
      && !(this.config as { useTimerFallback?: boolean }).useTimerFallback
    ) {
      this.scheduledFrameId = window.requestAnimationFrame(() => {
        this.scheduledFrameId = null;
        this.flushSync();
      });
    } else {
      // Fallback for SSR or timer-based test environments
      this.fallbackTimerId = setTimeout(() => {
        this.fallbackTimerId = null;
        this.flushSync();
      }, frameIntervalMs);
    }
  }

  public flushSync(): void {
    if (this.isDestroyed) {
      return;
    }

    this.cancelScheduled();

    if (this.buffer.length === 0) {
      return;
    }

    const mergedChunks = this.buffer.length;
    const combinedText = this.buffer.join('');
    this.buffer = [];
    this.bufferedCharsCount = 0;
    this.lastFlushTimestamp = Date.now();

    this.metrics.totalFramesRendered += 1;
    this.metrics.totalMergedChunks += (mergedChunks - 1);

    try {
      this.onRender(combinedText);
    } catch (err: unknown) {
      console.error('[StreamBackpressureController] Render callback failed:', err);
    }
  }

  public endStream(): void {
    this.flushSync();
  }

  private cancelScheduled(): void {
    if (this.scheduledFrameId !== null) {
      if (typeof window !== 'undefined' && typeof window.cancelAnimationFrame === 'function') {
        window.cancelAnimationFrame(this.scheduledFrameId);
      }
      this.scheduledFrameId = null;
    }

    if (this.fallbackTimerId !== null) {
      clearTimeout(this.fallbackTimerId);
      this.fallbackTimerId = null;
    }
  }

  public getMetrics(): Readonly<BackpressureMetrics> {
    return { ...this.metrics };
  }

  public destroy(): void {
    if (this.isDestroyed) {
      return;
    }
    this.isDestroyed = true;
    this.cancelScheduled();
    this.buffer = [];
    this.bufferedCharsCount = 0;
  }
}
