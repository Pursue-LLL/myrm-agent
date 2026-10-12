/**
 * Unit & Integration tests for MemoryInspectorDrawer component.
 *
 * [INPUT] MemoryInspectorDrawer component, mock memories, mock callbacks
 * [OUTPUT] Vitest test suite verifying drawer rendering and governance operations.
 * [POS] Item 30 unit tests. Strictly under 220 lines. Zero `any`.
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryInspectorDrawer } from './MemoryInspectorDrawer';
import type { EpistemicMemoryItem } from './memoryInspectorTypes';

describe('MemoryInspectorDrawer', () => {
  const mockMemories: EpistemicMemoryItem[] = [
    {
      id: 'm1',
      content: 'User preferences: Always respond in Chinese',
      epistemic_tier: 'assertion',
      confidence_score: 1.0,
      similarity_score: 0.95,
      hit_count: 5,
      created_at: '2026-08-01T00:00:00Z',
      provenance_chain: ['user prompt config'],
    },
    {
      id: 'm2',
      content: 'Agent inference: User prefers brief answers without preamble',
      epistemic_tier: 'belief',
      confidence_score: 0.6,
      similarity_score: 0.76,
      hit_count: 2,
      created_at: '2026-08-15T00:00:00Z',
      provenance_chain: ['heuristic summary'],
    },
  ];

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <MemoryInspectorDrawer
        isOpen={false}
        onClose={vi.fn()}
        memories={mockMemories}
        sessionId="session_42"
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer header, distribution stats, and memory cards when open', () => {
    render(
      <MemoryInspectorDrawer
        isOpen={true}
        onClose={vi.fn()}
        memories={mockMemories}
        sessionId="session_42"
      />
    );

    expect(screen.getByText('记忆透视镜与治理抽屉')).toBeInTheDocument();
    expect(screen.getByText(/session_42/)).toBeInTheDocument();
    expect(screen.getByText('共引用 2 条长程记忆')).toBeInTheDocument();
    expect(screen.getByText(/User preferences: Always respond in Chinese/)).toBeInTheDocument();
    expect(screen.getByText(/Agent inference: User prefers brief answers/)).toBeInTheDocument();
  });

  it('triggers onPromote callback when promote action is clicked on belief item', async () => {
    const onPromote = vi.fn();
    render(
      <MemoryInspectorDrawer
        isOpen={true}
        onClose={vi.fn()}
        memories={mockMemories}
        sessionId="session_42"
        onPromote={onPromote}
      />
    );

    const promoteBtn = screen.getByText('升格为事实');
    fireEvent.click(promoteBtn);

    expect(onPromote).toHaveBeenCalledWith('m2', 'assertion');
  });

  it('supports in-place text correction and calls onCorrect callback', async () => {
    const onCorrect = vi.fn();
    render(
      <MemoryInspectorDrawer
        isOpen={true}
        onClose={vi.fn()}
        memories={mockMemories}
        sessionId="session_42"
        onCorrect={onCorrect}
      />
    );

    const editBtns = screen.getAllByText('就地纠偏');
    fireEvent.click(editBtns[0]);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Corrected preferences text' } });

    const saveBtn = screen.getByText('保存修正');
    fireEvent.click(saveBtn);

    expect(onCorrect).toHaveBeenCalledWith('m1', 'Corrected preferences text');
  });

  it('triggers onForget callback when forget action is clicked', async () => {
    const onForget = vi.fn();
    render(
      <MemoryInspectorDrawer
        isOpen={true}
        onClose={vi.fn()}
        memories={mockMemories}
        sessionId="session_42"
        onForget={onForget}
      />
    );

    const forgetBtns = screen.getAllByText('物理遗忘');
    fireEvent.click(forgetBtns[0]);

    expect(onForget).toHaveBeenCalledWith('m1');
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();
    render(
      <MemoryInspectorDrawer
        isOpen={true}
        onClose={onClose}
        memories={mockMemories}
        sessionId="session_42"
      />
    );

    const closeBtn = screen.getByRole('button', { name: '关闭透视抽屉' });
    fireEvent.click(closeBtn);

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
