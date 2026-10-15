/**
 * [INPUT]
 * - vitest (POS: Test runner)
 * - @testing-library/react (POS: React DOM testing utilities)
 * - @/components/features/chat-window/memory-inspector/VisualMemoryHealthCard
 * - @/components/features/chat-window/memory-inspector/useMemoryInspectorStore
 *
 * [OUTPUT]
 * - Component unit tests for VisualMemoryHealthCard covering rendering, interactions, and a11y.
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { VisualMemoryHealthCard } from '../VisualMemoryHealthCard';
import { useMemoryInspectorStore } from '../useMemoryInspectorStore';

describe('VisualMemoryHealthCard', () => {
  beforeEach(() => {
    useMemoryInspectorStore.getState().resetStore();
    vi.restoreAllMocks();
  });

  it('renders default readiness status and core metadata correctly', () => {
    render(<VisualMemoryHealthCard />);

    expect(screen.getByTestId('visual-memory-health-card')).toBeInTheDocument();
    expect(screen.getByText('记忆引擎白盒就绪看板')).toBeInTheDocument();
    expect(screen.getByTestId('badge-status-ready')).toBeInTheDocument();

    expect(screen.getByTestId('label-model-name')).toHaveTextContent('text-embedding-3-small');
    expect(screen.getByTestId('label-vector-dims')).toHaveTextContent('1536 维');
    expect(screen.getByTestId('label-chunks-count')).toHaveTextContent('4,280');
    expect(screen.getByTestId('label-fts-count')).toHaveTextContent('3,950');
  });

  it('renders degraded and error status badges according to store health', () => {
    const { rerender } = render(<VisualMemoryHealthCard />);

    act(() => {
      useMemoryInspectorStore.getState().setEngineHealth({ status: 'degraded' });
    });
    rerender(<VisualMemoryHealthCard />);
    expect(screen.getByTestId('badge-status-degraded')).toBeInTheDocument();

    act(() => {
      useMemoryInspectorStore.getState().setEngineHealth({ status: 'error' });
    });
    rerender(<VisualMemoryHealthCard />);
    expect(screen.getByTestId('badge-status-error')).toBeInTheDocument();
  });

  it('runs deep diagnostic on button click and renders latency details panel', async () => {
    const onDiagnosticComplete = vi.fn();
    render(<VisualMemoryHealthCard onDiagnosticComplete={onDiagnosticComplete} />);

    const diagButton = screen.getByTestId('btn-deep-diagnostic');
    fireEvent.click(diagButton);

    await waitFor(() => {
      expect(screen.getByTestId('diagnostic-results-panel')).toBeInTheDocument();
    });

    expect(onDiagnosticComplete).toHaveBeenCalledTimes(1);

    expect(screen.getByTestId('diag-latency-embedding')).toBeInTheDocument();
    expect(screen.getByTestId('diag-latency-write')).toBeInTheDocument();
    expect(screen.getByTestId('diag-latency-cosine')).toBeInTheDocument();

    // Toggle collapse
    const toggleButton = screen.getByTestId('btn-toggle-diagnostic');
    fireEvent.click(toggleButton);

    expect(screen.queryByTestId('diag-latency-embedding')).not.toBeInTheDocument();
  });

  it('starts and cancels re-indexing process properly', () => {
    const onReindexStart = vi.fn();
    render(<VisualMemoryHealthCard onReindexStart={onReindexStart} />);

    expect(screen.queryByTestId('reindex-progress-container')).not.toBeInTheDocument();

    const reindexButton = screen.getByTestId('btn-force-reindex');
    fireEvent.click(reindexButton);

    expect(onReindexStart).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('reindex-progress-container')).toBeInTheDocument();
    expect(screen.getByTestId('reindex-progress-bar')).toBeInTheDocument();

    const cancelButton = screen.getByTestId('btn-cancel-reindex');
    fireEvent.click(cancelButton);

    expect(screen.queryByTestId('reindex-progress-container')).not.toBeInTheDocument();
  });
});
