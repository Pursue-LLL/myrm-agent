import React from 'react';
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SwarmModeToggle } from '../SwarmModeToggle';
import { useSwarmExecutionStore } from '@/components/features/swarm/useSwarmExecutionStore';

vi.mock('@/components/primitives/tooltip', () => ({
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

describe('SwarmModeToggle', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useSwarmExecutionStore.getState().reset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders default disabled toggle button', () => {
    render(<SwarmModeToggle chatId="chat_test_01" />);

    const button = screen.getByRole('button', { name: 'swarmModeAriaLabel' });
    expect(button).toBeDefined();
    expect(button.getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByText('swarmModeLabel')).toBeDefined();
  });

  it('toggles swarm mode on click and reveals quota badge', () => {
    render(<SwarmModeToggle chatId="chat_test_01" />);

    const button = screen.getByRole('button', { name: 'swarmModeAriaLabel' });
    fireEvent.click(button);

    expect(useSwarmExecutionStore.getState().isSwarmEnabled).toBe(true);
    expect(button.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('5')).toBeDefined(); // concurrency quota default 5

    // Click again to turn off
    fireEvent.click(button);
    expect(useSwarmExecutionStore.getState().isSwarmEnabled).toBe(false);
    expect(button.getAttribute('aria-pressed')).toBe('false');
  });
});
