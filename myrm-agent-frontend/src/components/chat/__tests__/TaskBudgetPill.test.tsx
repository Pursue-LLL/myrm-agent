/** @vitest-environment jsdom */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TaskBudgetPill } from '../TaskBudgetPill';

describe('TaskBudgetPill Component', () => {
  it('renders nothing when hardLimit is missing or zero', () => {
    const { container } = render(<TaskBudgetPill totalTokens={1000} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders normal status when token usage is below 80%', () => {
    render(<TaskBudgetPill totalTokens={5000} hardLimit={10000} />);
    expect(screen.getByTestId('task-budget-pill')).toBeInTheDocument();
    expect(screen.getByTestId('icon-normal')).toBeInTheDocument();
    expect(screen.getByText('5,000 / 10,000 (50%)')).toBeInTheDocument();
    expect(screen.queryByTestId('btn-extend-budget')).not.toBeInTheDocument();
  });

  it('renders warning status when token usage reaches 80%', () => {
    render(<TaskBudgetPill totalTokens={8500} hardLimit={10000} />);
    expect(screen.getByTestId('icon-warning')).toBeInTheDocument();
    expect(screen.getByText('8,500 / 10,000 (85%)')).toBeInTheDocument();
  });

  it('renders breach status and extend button when token usage reaches 100%', () => {
    const onExtend = vi.fn();
    render(<TaskBudgetPill totalTokens={10500} hardLimit={10000} onExtendBudget={onExtend} />);

    expect(screen.getByTestId('icon-breached')).toBeInTheDocument();
    const extendBtn = screen.getByTestId('btn-extend-budget');
    expect(extendBtn).toBeInTheDocument();

    fireEvent.click(extendBtn);
    expect(onExtend).toHaveBeenCalledWith(20000);
  });
});
