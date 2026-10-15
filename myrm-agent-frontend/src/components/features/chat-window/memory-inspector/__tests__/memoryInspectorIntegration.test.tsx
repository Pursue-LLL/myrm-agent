/**
 * [INPUT]
 * - vitest (POS: Test framework)
 * - @testing-library/react (POS: React component integration testing)
 * - @/components/features/chat-window/memory-inspector/VisualMemoryHealthCard
 * - @/components/features/chat-window/memory-inspector/useMemoryInspectorStore
 *
 * [OUTPUT]
 * - End-to-end integration test suite verifying diagnostics, custom event bus, and reindexing flows.
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { VisualMemoryHealthCard } from '../VisualMemoryHealthCard';
import { useMemoryInspectorStore } from '../useMemoryInspectorStore';
import type { DiagnosticLatencyBreakdown, ReindexProgress } from '../memoryInspectorTypes';

describe('memoryInspectorIntegration', () => {
  beforeEach(() => {
    useMemoryInspectorStore.getState().resetStore();
    vi.restoreAllMocks();
  });

  it('coordinates full diagnostic event dispatch and UI rendering roundtrip', async () => {
    const receivedEvents: Array<{
      action: string;
      diagnostic?: DiagnosticLatencyBreakdown;
      progress?: ReindexProgress;
    }> = [];

    const handleCustomEvent = (event: Event) => {
      const customEvent = event as CustomEvent<{
        action: string;
        diagnostic?: DiagnosticLatencyBreakdown;
        progress?: ReindexProgress;
      }>;
      if (customEvent.detail) {
        receivedEvents.push(customEvent.detail);
      }
    };

    window.addEventListener('myrm:memory-inspector-diagnostic', handleCustomEvent);

    render(<VisualMemoryHealthCard />);

    // 1. Initial State Check
    expect(screen.getByTestId('badge-status-ready')).toBeInTheDocument();

    // 2. Click Deep Diagnostic
    const diagBtn = screen.getByTestId('btn-deep-diagnostic');
    fireEvent.click(diagBtn);

    await waitFor(() => {
      expect(screen.getByTestId('diagnostic-results-panel')).toBeInTheDocument();
    });

    // 3. Verify Event Bus Dispatch
    const diagEvent = receivedEvents.find((e) => e.action === 'deep_diagnostic');
    expect(diagEvent).toBeDefined();
    expect(diagEvent?.diagnostic?.totalMs).toBeGreaterThan(0);

    window.removeEventListener('myrm:memory-inspector', handleCustomEvent);
  });

  it('coordinates reindex progression through partial chunks updates to completion', () => {
    const receivedEvents: Array<{
      action: string;
      progress?: ReindexProgress;
    }> = [];

    const handleCustomEvent = (event: Event) => {
      const customEvent = event as CustomEvent<{
        action: string;
        progress?: ReindexProgress;
      }>;
      if (customEvent.detail) {
        receivedEvents.push(customEvent.detail);
      }
    };

    window.addEventListener('myrm:memory-inspector-diagnostic', handleCustomEvent);

    render(<VisualMemoryHealthCard />);

    // Start Reindex
    fireEvent.click(screen.getByTestId('btn-force-reindex'));
    expect(screen.getByTestId('reindex-progress-container')).toBeInTheDocument();

    // Progress to 50%
    act(() => {
      useMemoryInspectorStore.getState().updateReindexProgress(2140);
    });

    expect(screen.getByText(/向量重索引中：50%/)).toBeInTheDocument();
    expect(screen.getByTestId('reindex-progress-bar')).toHaveStyle({ width: '50%' });

    // Progress to completion
    act(() => {
      useMemoryInspectorStore.getState().completeReindexing();
    });

    const completeEvent = receivedEvents.find((e) => e.action === 'reindex_complete');
    expect(completeEvent).toBeDefined();
    expect(completeEvent?.progress?.progressPercent).toBe(100);

    window.removeEventListener('myrm:memory-inspector', handleCustomEvent);
  });

  it('reflects dynamic degradation and restore cycle cleanly', () => {
    render(<VisualMemoryHealthCard />);

    // Engine degraded
    act(() => {
      useMemoryInspectorStore.getState().setEngineHealth({
        status: 'degraded',
        modelName: 'fallback-minilm-l6',
      });
    });

    expect(screen.getByTestId('badge-status-degraded')).toBeInTheDocument();
    expect(screen.getByTestId('label-model-name')).toHaveTextContent('fallback-minilm-l6');

    // Restore to normal
    act(() => {
      useMemoryInspectorStore.getState().setEngineHealth({
        status: 'ready',
        modelName: 'text-embedding-3-small',
      });
    });

    expect(screen.getByTestId('badge-status-ready')).toBeInTheDocument();
    expect(screen.getByTestId('label-model-name')).toHaveTextContent('text-embedding-3-small');
  });
});
