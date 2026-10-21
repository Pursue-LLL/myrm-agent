/** @vitest-environment jsdom */
'use client';

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import LeaseProgressCapsule from '../LeaseProgressCapsule';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';

const mockApiRequest = vi.fn();

vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => mockApiRequest(...args),
}));

describe('LeaseProgressCapsule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiRequest.mockResolvedValue({ ok: true, paused: true });
    useDesktopControlApprovalStore.setState({
      activeEnvelope: {
        taskId: 'task-capsule-1',
        allowedApps: ['TextEdit'],
        maxActions: 30,
        usedActions: 5,
        remainingBudget: 25,
        allowSystemDialogs: true,
        status: 'active',
        canExtend: true,
        hardLimit: 100,
      },
    });
  });

  it('renders nothing when activeEnvelope is null', () => {
    useDesktopControlApprovalStore.setState({ activeEnvelope: null });
    const { container } = render(<LeaseProgressCapsule />);
    expect(container.firstChild).toBeNull();
  });

  it('renders current envelope quota and pause button', () => {
    render(<LeaseProgressCapsule />);
    expect(screen.getByText('免打扰配额: 5/30 步')).toBeInTheDocument();
    expect(screen.getByTestId('pause-lease-btn')).toBeInTheDocument();
  });

  it('posts pause decision and clears activeEnvelope when pause button is clicked', async () => {
    render(<LeaseProgressCapsule />);

    const pauseBtn = screen.getByTestId('pause-lease-btn');
    await act(async () => {
      fireEvent.click(pauseBtn);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(mockApiRequest).toHaveBeenCalledWith('/webui/desktop/envelope/pause', {
        method: 'POST',
        body: JSON.stringify({ task_id: 'task-capsule-1' }),
      });
      expect(useDesktopControlApprovalStore.getState().activeEnvelope).toBeNull();
    });
  });

  it('renders extend button when nearing limit and extends budget on click', async () => {
    useDesktopControlApprovalStore.setState({
      activeEnvelope: {
        taskId: 'task-capsule-2',
        allowedApps: ['TextEdit'],
        maxActions: 30,
        usedActions: 28,
        remainingBudget: 2,
        allowSystemDialogs: true,
        status: 'active',
        canExtend: true,
        hardLimit: 100,
      },
    });

    render(<LeaseProgressCapsule />);
    const extendBtn = screen.getByTestId('extend-lease-btn');
    expect(extendBtn).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(extendBtn);
    });

    expect(useDesktopControlApprovalStore.getState().activeEnvelope?.maxActions).toBe(40);
  });
});
