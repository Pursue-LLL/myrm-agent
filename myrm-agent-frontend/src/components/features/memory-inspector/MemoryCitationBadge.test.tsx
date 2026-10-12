/**
 * Unit tests for MemoryCitationBadge component.
 *
 * [INPUT] MemoryCitationBadge component, mock memories, callbacks
 * [OUTPUT] Vitest test suite verifying citation rendering and click behavior.
 * [POS] Item 30 unit tests. Strictly under 120 lines. Zero `any`.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { MemoryCitationBadge } from './MemoryCitationBadge';
import { useMemoryInspectorStore } from '@/store/useMemoryInspectorStore';
import type { EpistemicMemoryItem } from './memoryInspectorTypes';

describe('MemoryCitationBadge', () => {
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
    {
      id: 'm2',
      content: 'OS is macOS Sonoma',
      epistemic_tier: 'observation',
      confidence_score: 0.85,
      similarity_score: 0.88,
      hit_count: 4,
      created_at: '2026-08-10T00:00:00Z',
      provenance_chain: ['uname tool'],
    },
    {
      id: 'm3',
      content: 'User prefers concise summaries',
      epistemic_tier: 'belief',
      confidence_score: 0.6,
      similarity_score: 0.75,
      hit_count: 2,
      created_at: '2026-08-15T00:00:00Z',
      provenance_chain: ['prompt inference'],
    },
  ];

  it('renders nothing when memories array is empty', () => {
    const { container } = render(<MemoryCitationBadge memories={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders citation count and color dots when memories are provided', () => {
    render(<MemoryCitationBadge memories={mockMemories} sessionId="session_test" />);
    expect(screen.getByText('引用 3 条记忆')).toBeInTheDocument();
  });

  it('calls custom onClick callback when clicked', () => {
    const onClick = vi.fn();
    render(<MemoryCitationBadge memories={mockMemories} onClick={onClick} />);

    const badge = screen.getByRole('button', { name: /查看引用 3 条记忆/ });
    fireEvent.click(badge);

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('opens inspector drawer in store by default when clicked', () => {
    render(<MemoryCitationBadge memories={mockMemories} sessionId="session_test" />);

    const badge = screen.getByRole('button', { name: /查看引用 3 条记忆/ });
    fireEvent.click(badge);

    const state = useMemoryInspectorStore.getState();
    expect(state.isOpen).toBe(true);
    expect(state.sessionId).toBe('session_test');
    expect(state.memories.length).toBe(3);
  });
});
