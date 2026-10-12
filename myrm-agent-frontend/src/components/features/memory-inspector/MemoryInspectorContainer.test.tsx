/**
 * Unit tests for MemoryInspectorContainer.
 *
 * [INPUT] MemoryInspectorContainer component, useMemoryInspectorStore
 * [OUTPUT] Vitest test suite verifying container lifecycle and event listeners.
 * [POS] Item 30 container tests. Strictly under 120 lines. Zero `any`.
 */

import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { MemoryInspectorContainer } from './MemoryInspectorContainer';
import { useMemoryInspectorStore } from '@/store/useMemoryInspectorStore';
import type { EpistemicMemoryItem } from './memoryInspectorTypes';

describe('MemoryInspectorContainer', () => {
  beforeEach(() => {
    act(() => {
      useMemoryInspectorStore.getState().closeInspector();
    });
  });

  const mockMemories: EpistemicMemoryItem[] = [
    {
      id: 'm1',
      content: 'Rule 1: Always respond in Chinese',
      epistemic_tier: 'assertion',
      confidence_score: 1.0,
      similarity_score: 0.95,
      hit_count: 8,
      created_at: '2026-08-01T00:00:00Z',
      provenance_chain: ['user_rule'],
    },
  ];

  it('renders nothing when drawer is closed in store', () => {
    const { container } = render(<MemoryInspectorContainer />);
    expect(container.firstChild).toBeNull();
  });

  it('renders inspector drawer when store isOpen is true', () => {
    act(() => {
      useMemoryInspectorStore.getState().openInspector('session_1', mockMemories);
    });

    render(<MemoryInspectorContainer />);
    expect(screen.getByText('记忆透视镜与治理抽屉')).toBeInTheDocument();
    expect(screen.getByText(/Rule 1: Always respond in Chinese/)).toBeInTheDocument();
  });

  it('opens drawer in response to "myrm:open-memory-inspector" custom event', () => {
    render(<MemoryInspectorContainer />);
    expect(screen.queryByText('记忆透视镜与治理抽屉')).not.toBeInTheDocument();

    act(() => {
      window.dispatchEvent(
        new CustomEvent('myrm:open-memory-inspector', {
          detail: {
            sessionId: 'session_event',
            memories: mockMemories,
          },
        })
      );
    });

    expect(screen.getByText('记忆透视镜与治理抽屉')).toBeInTheDocument();
  });
});
