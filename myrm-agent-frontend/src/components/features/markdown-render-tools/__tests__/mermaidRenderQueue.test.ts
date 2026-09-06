// @vitest-environment jsdom
/**
 * [INPUT] mermaidRenderQueue.ts
 * [OUTPUT] Unit tests validating serial queue execution order, 10s watchdog timeout rejection, DOM cleanup, and 1-shot retry
 * [POS] Unit tests for Mermaid serial render watchdog queue
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  globalMermaidRenderQueue,
  MermaidRenderTimeoutError,
} from '../mermaidRenderQueue';

describe('MermaidRenderQueue', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders tasks sequentially without concurrent overlapping', async () => {
    const executionOrder: string[] = [];
    let concurrentRunning = 0;
    let maxConcurrent = 0;

    const mockMermaidLib = {
      render: vi.fn(async (id: string, code: string) => {
        concurrentRunning += 1;
        maxConcurrent = Math.max(maxConcurrent, concurrentRunning);
        executionOrder.push(`start-${id}`);
        await new Promise((r) => setTimeout(r, 20));
        executionOrder.push(`end-${id}`);
        concurrentRunning -= 1;
        return { svg: `<svg id="${id}">${code}</svg>` };
      }),
    };

    const task1 = globalMermaidRenderQueue.render(mockMermaidLib as any, 'chart-1', 'graph TD; A-->B;');
    const task2 = globalMermaidRenderQueue.render(mockMermaidLib as any, 'chart-2', 'graph TD; C-->D;');
    const task3 = globalMermaidRenderQueue.render(mockMermaidLib as any, 'chart-3', 'graph TD; E-->F;');

    const results = await Promise.all([task1, task2, task3]);

    expect(results[0].svg).toContain('chart-1');
    expect(results[1].svg).toContain('chart-2');
    expect(results[2].svg).toContain('chart-3');

    // Concurrency must never exceed 1
    expect(maxConcurrent).toBe(1);

    // Strict sequential execution
    expect(executionOrder).toEqual([
      'start-chart-1',
      'end-chart-1',
      'start-chart-2',
      'end-chart-2',
      'start-chart-3',
      'end-chart-3',
    ]);
  });

  it('triggers watchdog timeout rejection and cleans orphan DOM if render hangs', async () => {
    const mockMermaidLib = {
      render: vi.fn(async (id: string) => {
        // Create orphan DOM elements that mermaid would inject
        const el = document.createElement('div');
        el.id = `d${id}`;
        document.body.appendChild(el);

        // Never resolves (simulating mermaid v11 hang)
        return new Promise<{ svg: string }>(() => {});
      }),
    };

    // Use a short 50ms watchdog timeout for the test
    const renderPromise = globalMermaidRenderQueue.render(
      mockMermaidLib as any,
      'hung-chart',
      'graph TD; Hang-->Forever;',
      50,
    );

    await expect(renderPromise).rejects.toThrow(MermaidRenderTimeoutError);
    // Orphan DOM element should have been removed
    expect(document.getElementById('dhung-chart')).toBeNull();
  });

  it('recovers automatically with 1-shot retry on transient error', async () => {
    let attempts = 0;
    const mockMermaidLib = {
      render: vi.fn(async (id: string) => {
        attempts += 1;
        if (attempts === 1) {
          throw new Error('Transient DOM contention');
        }
        return { svg: `<svg id="${id}">recovered</svg>` };
      }),
    };

    const result = await globalMermaidRenderQueue.render(
      mockMermaidLib as any,
      'retry-chart',
      'graph TD; Retry-->Pass;',
      500,
    );

    expect(attempts).toBe(2);
    expect(result.svg).toContain('recovered');
  });
});
