import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { useModelPacingStore } from '../useModelPacingStore';
import { ModelPacingSelectorPill } from '../ModelPacingSelectorPill';

describe('ModelPacingSelectorPill', () => {
  beforeEach(() => {
    act(() => {
      useModelPacingStore.getState().resetStore();
    });
  });

  it('renders default balanced pacing pill', () => {
    render(<ModelPacingSelectorPill />);
    const button = screen.getByRole('button', { name: /执行节奏：平衡推荐/ });
    expect(button).toBeInTheDocument();
    expect(screen.getByText('平衡推荐')).toBeInTheDocument();
    expect(screen.getByText('10-25s')).toBeInTheDocument();
  });

  it('reflects fast tier with low-latency badge', () => {
    act(() => {
      useModelPacingStore.getState().setPacingTier('fast');
    });

    render(<ModelPacingSelectorPill />);
    const button = screen.getByRole('button', { name: /执行节奏：极速日常/ });
    expect(button).toBeInTheDocument();
    expect(screen.getByText('极速日常')).toBeInTheDocument();
    expect(screen.getByText('< 5s')).toBeInTheDocument();
  });

  it('reflects smart tier with deep reasoning badge', () => {
    act(() => {
      useModelPacingStore.getState().setPacingTier('smart');
    });

    render(<ModelPacingSelectorPill />);
    const button = screen.getByRole('button', { name: /执行节奏：深度推理/ });
    expect(button).toBeInTheDocument();
    expect(screen.getByText('深度推理')).toBeInTheDocument();
    expect(screen.getByText('30-90s')).toBeInTheDocument();
  });

  it('toggles popover on click', () => {
    render(<ModelPacingSelectorPill />);
    const button = screen.getByRole('button', { name: /执行节奏/ });
    expect(button).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(button);
    expect(useModelPacingStore.getState().isPopoverOpen).toBe(true);

    fireEvent.click(button);
    expect(useModelPacingStore.getState().isPopoverOpen).toBe(false);
  });

  it('hides label in compact mode', () => {
    render(<ModelPacingSelectorPill compact />);
    expect(screen.queryByText('平衡推荐')).not.toBeInTheDocument();
    expect(screen.getByText('10-25s')).toBeInTheDocument();
  });
});
