import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';
import { IntentEnvelopeCard } from '../IntentEnvelopeCard';
import { LeaseProgressCapsule } from '../LeaseProgressCapsule';

describe('IntentEnvelopeCard & LeaseProgressCapsule', () => {
  beforeEach(() => {
    useDesktopControlApprovalStore.getState().clear();
    useDesktopControlApprovalStore.getState().setEnvelope(null);
  });

  it('renders pre-flight envelope details correctly', () => {
    render(<IntentEnvelopeCard taskId="task_test_1" allowedApps={['Microsoft Excel', 'WeChat']} maxActions={20} />);

    expect(screen.getByText('受限意图包络线全局授权')).toBeInTheDocument();
    expect(screen.getByText('Microsoft Excel')).toBeInTheDocument();
    expect(screen.getByText('WeChat')).toBeInTheDocument();
    expect(screen.getByText('20 步')).toBeInTheDocument();
  });

  it('activates envelope in store on clicking approve', () => {
    const onApprove = vi.fn();
    render(
      <IntentEnvelopeCard
        taskId="task_test_2"
        allowedApps={['Google Chrome']}
        maxActions={15}
        onApproveFastPath={onApprove}
      />,
    );

    const approveBtn = screen.getByRole('button', { name: /批准全速推进/i });
    fireEvent.click(approveBtn);

    expect(onApprove).toHaveBeenCalledTimes(1);
    const storeState = useDesktopControlApprovalStore.getState();
    expect(storeState.activeEnvelope).toEqual(
      expect.objectContaining({
        taskId: 'task_test_2',
        allowedApps: ['Google Chrome'],
        maxActions: 15,
        status: 'active',
      }),
    );
  });

  it('renders lease progress capsule and allows extending lease', () => {
    const onExtend = vi.fn();
    useDesktopControlApprovalStore.getState().setEnvelope({
      taskId: 'task_test_3',
      allowedApps: ['Chrome'],
      maxActions: 10,
      usedActions: 8,
      remainingBudget: 2,
      allowSystemDialogs: true,
      status: 'active',
    });

    render(<LeaseProgressCapsule onExtend={onExtend} />);

    expect(screen.getByText(/配额: 8\/10 步/i)).toBeInTheDocument();
    const extendBtn = screen.getByTestId('extend-lease-btn');
    expect(extendBtn).toBeInTheDocument();

    fireEvent.click(extendBtn);
    expect(onExtend).toHaveBeenCalledWith(10);

    const updated = useDesktopControlApprovalStore.getState().activeEnvelope;
    expect(updated?.maxActions).toBe(20);
    expect(updated?.remainingBudget).toBe(12);
  });
});
