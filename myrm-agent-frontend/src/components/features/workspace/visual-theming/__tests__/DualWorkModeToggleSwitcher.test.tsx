import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { DualWorkModeToggleSwitcher } from '../DualWorkModeToggleSwitcher';
import { useWorkspaceThemingStore } from '../useWorkspaceThemingStore';

describe('DualWorkModeToggleSwitcher', () => {
  beforeEach(() => {
    useWorkspaceThemingStore.getState().reset();
  });

  it('renders dual mode toggle buttons with default coding mode selected', () => {
    render(<DualWorkModeToggleSwitcher />);

    expect(
      screen.getByTestId('dual-work-mode-switcher'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '切换至编程极客模式' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '切换至通用办公模式' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Dev')).toBeInTheDocument();
  });

  it('switches to work mode and calls onModeChange callback', () => {
    const handleModeChange = vi.fn();
    render(<DualWorkModeToggleSwitcher onModeChange={handleModeChange} />);

    const workBtn = screen.getByRole('button', {
      name: '切换至通用办公模式',
    });
    act(() => {
      fireEvent.click(workBtn);
    });

    expect(handleModeChange).toHaveBeenCalledTimes(1);
    expect(handleModeChange).toHaveBeenCalledWith('work');
    expect(useWorkspaceThemingStore.getState().currentMode).toBe('work');
    expect(screen.getByText('Work')).toBeInTheDocument();
  });

  it('switches back to coding mode seamlessly', () => {
    useWorkspaceThemingStore.getState().switchMode('work');
    render(<DualWorkModeToggleSwitcher />);

    const codingBtn = screen.getByRole('button', {
      name: '切换至编程极客模式',
    });
    act(() => {
      fireEvent.click(codingBtn);
    });

    expect(useWorkspaceThemingStore.getState().currentMode).toBe('coding');
    expect(screen.getByText('Dev')).toBeInTheDocument();
  });
});
