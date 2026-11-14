import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import ThinkingBudgetEffortSlider from '../ThinkingBudgetEffortSlider';
import { useThinkingBudgetStore } from '../useThinkingBudgetStore';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'zh'));

describe('ThinkingBudgetEffortSlider', () => {
  beforeEach(() => {
    localStorage.clear();
    useThinkingBudgetStore.setState({
      level: 'auto',
      currentModel: 'claude-3-7-sonnet',
      tokenBudget: 0,
      reasoningEffort: undefined,
    });
  });

  it('renders all step pills and title badge', () => {
    render(<ThinkingBudgetEffortSlider modelName="claude-3-7-sonnet" supportsReasoning={true} />);

    expect(screen.getByText('思考深度')).toBeDefined();
    expect(screen.getByTestId('thinking-step-auto')).toBeDefined();
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
    fireEvent.change(rangeInput, { target: { value: '4' } });

    expect(useThinkingBudgetStore.getState().level).toBe('high');
    expect(useThinkingBudgetStore.getState().tokenBudget).toBe(16384);
  });

  it('starts on auto, which is named rather than measured, and is the first stop of the slider', () => {
    render(<ThinkingBudgetEffortSlider modelName="claude-3-7-sonnet" supportsReasoning={true} />);

    expect(screen.getByTestId('thinking-step-auto').textContent).toBe('自动');
    expect(screen.getByTestId('thinking-tier-badge').textContent).toBe('自动');
    expect((screen.getByTestId('thinking-range-input') as HTMLInputElement).value).toBe('0');
    expect(screen.getByTestId('thinking-step-auto').getAttribute('aria-pressed')).toBe('true');
  });

  it('keeps off apart from auto: off is the zero budget the user asked for', () => {
    render(<ThinkingBudgetEffortSlider modelName="claude-3-7-sonnet" supportsReasoning={true} />);

    fireEvent.click(screen.getByTestId('thinking-step-off'));

    expect(useThinkingBudgetStore.getState().level).toBe('off');
    expect(screen.getByTestId('thinking-tier-badge').textContent).toBe('0k');
    expect((screen.getByTestId('thinking-range-input') as HTMLInputElement).value).toBe('1');
  });

  it('reaches every tier from the native range slider', () => {
    render(<ThinkingBudgetEffortSlider modelName="claude-3-7-sonnet" supportsReasoning={true} />);
    const rangeInput = screen.getByTestId('thinking-range-input') as HTMLInputElement;

    expect(rangeInput.max).toBe('5');
    // Each stop differs from the one before, so every change is a real move of the slider.
    for (const [value, level] of [
      ['1', 'off'],
      ['2', 'low'],
      ['3', 'medium'],
      ['4', 'high'],
      ['5', 'max'],
      ['0', 'auto'],
    ] as const) {
      fireEvent.change(rangeInput, { target: { value } });
      expect(useThinkingBudgetStore.getState().level).toBe(level);
    }
  });

  it('renders unsupported indicator when supportsReasoning is false', () => {
    render(<ThinkingBudgetEffortSlider modelName="gpt-3.5-turbo" supportsReasoning={false} />);

    expect(screen.getByText('不支持')).toBeDefined();
    expect(screen.queryByTestId('thinking-range-input')).toBeNull();
  });
});
