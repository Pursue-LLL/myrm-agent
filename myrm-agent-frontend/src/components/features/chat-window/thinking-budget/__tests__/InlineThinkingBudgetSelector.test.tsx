import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InlineThinkingBudgetSelector } from '../InlineThinkingBudgetSelector';
import { useThinkingBudgetStore } from '../useThinkingBudgetStore';

describe('InlineThinkingBudgetSelector', () => {
  beforeEach(() => {
    useThinkingBudgetStore.getState().reset();
  });

  it('renders nothing when isThinkingCapable is false', () => {
    useThinkingBudgetStore.getState().setIsThinkingCapable(false);
    render(<InlineThinkingBudgetSelector />);

    expect(screen.queryByRole('button', { name: '选择模型深度思考预算' })).not.toBeInTheDocument();
  });

  it('renders budget trigger button with current level label', () => {
    render(<InlineThinkingBudgetSelector />);

    const btn = screen.getByRole('button', { name: '选择模型深度思考预算' });
    expect(btn).toBeInTheDocument();
    expect(screen.getByText('标准思考 (~8k)')).toBeInTheDocument();
  });

  it('opens popover on click and lists all budget options', () => {
    render(<InlineThinkingBudgetSelector />);

    const btn = screen.getByRole('button', { name: '选择模型深度思考预算' });
    fireEvent.click(btn);

    expect(screen.getByText('自适应推理预算设定')).toBeInTheDocument();
    expect(screen.getByText('关闭思考')).toBeInTheDocument();
    expect(screen.getByText('快速直觉 (~1k)')).toBeInTheDocument();
    expect(screen.getByText('深度攻坚 (~32k)')).toBeInTheDocument();
  });

  it('switches to high budget when clicking high option', () => {
    render(<InlineThinkingBudgetSelector />);

    const btn = screen.getByRole('button', { name: '选择模型深度思考预算' });
    fireEvent.click(btn);

    const highOption = screen.getByText('深度攻坚 (~32k)');
    fireEvent.click(highOption);

    expect(useThinkingBudgetStore.getState().currentBudgetLevel).toBe('high');
    expect(useThinkingBudgetStore.getState().isSelectorOpen).toBe(false);
  });
});
