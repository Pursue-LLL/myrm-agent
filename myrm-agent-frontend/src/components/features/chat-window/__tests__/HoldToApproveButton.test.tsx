import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { HoldToApproveButton } from '../mobile/HoldToApproveButton';

describe('HoldToApproveButton', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders with label and icon', () => {
    render(<HoldToApproveButton label="Approve All" onTrigger={vi.fn()} />);
    expect(screen.getByText('Approve All')).toBeInTheDocument();
  });

  it('does not trigger on brief press', () => {
    const onTrigger = vi.fn();
    render(<HoldToApproveButton label="Approve All" onTrigger={onTrigger} durationMs={500} />);

    const button = screen.getByRole('button');
    fireEvent.pointerDown(button);

    act(() => {
      vi.advanceTimersByTime(200);
    });

    fireEvent.pointerUp(button);

    expect(onTrigger).not.toHaveBeenCalled();
  });

  it('triggers onTrigger when held for the full duration', () => {
    const onTrigger = vi.fn();
    render(<HoldToApproveButton label="Approve All" onTrigger={onTrigger} durationMs={500} />);

    const button = screen.getByRole('button');
    fireEvent.pointerDown(button);

    act(() => {
      vi.advanceTimersByTime(550);
    });

    expect(onTrigger).toHaveBeenCalledTimes(1);
  });

  it('cancels when pointer leaves before completion', () => {
    const onTrigger = vi.fn();
    render(<HoldToApproveButton label="Approve All" onTrigger={onTrigger} durationMs={500} />);

    const button = screen.getByRole('button');
    fireEvent.pointerDown(button);

    act(() => {
      vi.advanceTimersByTime(300);
    });

    fireEvent.pointerLeave(button);

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(onTrigger).not.toHaveBeenCalled();
  });

  it('cancels when pointer event is cancelled (e.g. touch scroll)', () => {
    const onTrigger = vi.fn();
    render(<HoldToApproveButton label="Approve All" onTrigger={onTrigger} durationMs={500} />);

    const button = screen.getByRole('button');
    fireEvent.pointerDown(button);

    act(() => {
      vi.advanceTimersByTime(300);
    });

    fireEvent.pointerCancel(button);

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(onTrigger).not.toHaveBeenCalled();
  });
});
