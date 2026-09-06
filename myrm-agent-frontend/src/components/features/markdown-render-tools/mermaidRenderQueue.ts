/**
 * Global Mermaid Serial Render Queue and 10s Watchdog
 *
 * [WHY]
 * mermaid.js (especially v11+) uses internal temporary DOM elements during `render()`
 * and does not support concurrent renders. When multiple diagrams or documents render concurrently,
 * DOM race conditions cause pending promises that never resolve or reject, permanently locking up the UI.
 *
 * [HOW]
 * 1. Global serial queue executes render tasks strictly sequentially (concurrency = 1).
 * 2. 10s Watchdog timer rejects hung tasks and cleans orphaned temporary DOM elements.
 * 3. 1-shot auto-retry with DOM cleanup before throwing non-blocking error.
 */

import type mermaid from 'mermaid';

type MermaidLib = typeof mermaid;

export interface MermaidRenderResult {
  svg: string;
}

export class MermaidRenderTimeoutError extends Error {
  constructor(message = 'Mermaid render timed out after 10000ms watchdog') {
    super(message);
    this.name = 'MermaidRenderTimeoutError';
  }
}

interface QueueTask {
  chartId: string;
  code: string;
  mermaidLib: MermaidLib;
  timeoutMs: number;
  resolve: (result: MermaidRenderResult) => void;
  reject: (reason: unknown) => void;
}

const DEFAULT_WATCHDOG_TIMEOUT_MS = 10_000;

class MermaidRenderQueue {
  private queue: QueueTask[] = [];
  private isProcessing = false;

  public async render(
    mermaidLib: MermaidLib,
    chartId: string,
    code: string,
    timeoutMs = DEFAULT_WATCHDOG_TIMEOUT_MS,
  ): Promise<MermaidRenderResult> {
    return new Promise<MermaidRenderResult>((resolve, reject) => {
      this.queue.push({
        chartId,
        code,
        mermaidLib,
        timeoutMs,
        resolve,
        reject,
      });
      void this.processQueue();
    });
  }

  private cleanOrphanDom(chartId: string): void {
    if (typeof document === 'undefined') {
      return;
    }
    // Clean potential leftover containers created by mermaid
    const el = document.getElementById(chartId) ?? document.getElementById(`d${chartId}`);
    if (el) {
      el.remove();
    }
    // Also sweep dangling temporary svg / div injected into body
    const dangling = document.querySelectorAll(`[id*="${chartId}"]`);
    dangling.forEach((node) => node.remove());
  }

  private async executeWithWatchdog(task: QueueTask, attempt: number): Promise<MermaidRenderResult> {
    const { chartId, code, mermaidLib, timeoutMs } = task;

    let timer: ReturnType<typeof setTimeout> | null = null;
    const timeoutPromise = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {
        this.cleanOrphanDom(chartId);
        reject(new MermaidRenderTimeoutError(`Mermaid rendering hung (> ${timeoutMs}ms) for ${chartId}`));
      }, timeoutMs);
    });

    try {
      const renderPromise = mermaidLib.render(chartId, code);
      const res = await Promise.race([renderPromise, timeoutPromise]);
      return res;
    } catch (err) {
      this.cleanOrphanDom(chartId);
      if (attempt === 1) {
        // Auto-retry once on transient concurrency or DOM contention
        return this.executeWithWatchdog(task, 2);
      }
      throw err;
    } finally {
      if (timer) {
        clearTimeout(timer);
      }
    }
  }

  private async processQueue(): Promise<void> {
    if (this.isProcessing || this.queue.length === 0) {
      return;
    }

    this.isProcessing = true;
    const task = this.queue.shift();

    if (!task) {
      this.isProcessing = false;
      return;
    }

    try {
      const result = await this.executeWithWatchdog(task, 1);
      task.resolve(result);
    } catch (err) {
      task.reject(err);
    } finally {
      this.isProcessing = false;
      // Process next in queue asynchronously
      queueMicrotask(() => {
        void this.processQueue();
      });
    }
  }
}

export const globalMermaidRenderQueue = new MermaidRenderQueue();
