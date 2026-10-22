import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import ThinkingBudgetEffortSlider from '../ThinkingBudgetEffortSlider';
import { useThinkingBudgetStore } from '../useThinkingBudgetStore';

describe('ThinkingBudgetEffortSlider', () => {
  beforeEach(() => {
    localStorage.clear();
    useThinkingBudgetStore.setState({
      level: 'off',
      currentModel: 'claude-3-7-sonnet',
      tokenBudget: 0,
      reasoningEffort: undefined,
    });
  });

  it('renders all step pills and title badge', () => {
    render(<ThinkingBudgetEffortSlider modelName="claude-3-7-sonnet" supportsReasoning={true} />);

    expect(screen.getByText('思考深度')).toBeDefined();
    expect(screen.getByTestId('thinking-step-off')).toBeDefined();
    expect(screen.getByTestId('thinking-step-low')).toBeDefined();
    expect(screen.getByTestId('thinking-step-medium')).toBeDefined();
    expect(screen.getByTestId('thinking-step-high')).toBeDefined();
    expect(screen.getByTestId('thinking-step-max')).toBeDefined();
  });

  it('switches level when clicking a step pill', () => {
    render(<ThinkingBudgetEffortSlider modelName="claude-3-7-sonnet" supportsReasoning={true} />);

    const stepMedium = screen.getByTestId('thinking-step-medium');
    fireEvent.click(stepMedium);

    expect(useThinkingBudgetStore.getState().level).toBe('medium');
    expect(useThinkingBudgetStore.getState().tokenBudget).toBe(8192);

    const badge = screen.getByTestId('thinking-tier-badge');
    expect(badge.textContent).toBe('8k');
  });

  it('switches level using the native range slider input', () => {
    render(<ThinkingBudgetEffortSlider modelName="claude-3-7-sonnet" supportsReasoning={true} />);

    const rangeInput = screen.getByTestId('thinking-range-input') as HTMLInputElement;
    fireEvent.change(rangeInput, { target: { value: '3' } });

    expect(useThinkingBudgetStore.getState().level).toBe('high');
    expect(useThinkingBudgetStore.getState().tokenBudget).toBe(16384);
  });

  it('renders unsupported indicator when supportsReasoning is false', () => {
    render(<ThinkingBudgetEffortSlider modelName="gpt-3.5-turbo" supportsReasoning={false} />);

    expect(screen.getByText('不支持')).toBeDefined();
    expect(screen.queryByTestId('thinking-range-input')).toBeNull();
  });
});
