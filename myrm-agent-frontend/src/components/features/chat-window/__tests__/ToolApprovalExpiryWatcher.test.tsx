import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import useToolApprovalStore from '@/store/useToolApprovalStore';
import { elapse, startFakeClock, stopFakeClock } from '@/test-utils/fakeClock';

import ToolApprovalExpiryWatcher from '../ToolApprovalExpiryWatcher';
import { approvalRequest, kit } from './approvalKit';

vi.mock('sonner', async () => (await import('./approvalKit')).sonnerMock());
vi.mock('@/lib/approval/resumeApprovalStream', async (importOriginal) =>
  (await import('./approvalKit')).resumeMock(await importOriginal()),
);

const queueIds = () => useToolApprovalStore.getState().queue.map((request) => request.requestId);
const decisions = (call = 0) =>
  (kit.resume.mock.calls[call][1] as { decisions: Array<{ type: string; feedback?: string }> }).decisions;
const secondsFromNow = (seconds: number) => Math.floor(Date.now() / 1000) + seconds;

function watch(...requests: ReturnType<typeof approvalRequest>[]) {
  useToolApprovalStore.setState({ queue: requests });
  return render(<ToolApprovalExpiryWatcher />);
}

beforeEach(() => {
  vi.resetAllMocks();
  kit.resume.mockResolvedValue(undefined);
  useToolApprovalStore.setState({ queue: [], batchDecisions: new Map(), isResolving: false });
  startFakeClock();
});

afterEach(() => {
  stopFakeClock();
});

describe('ToolApprovalExpiryWatcher', () => {
  it('does nothing, and keeps no timer running, while no approval is waiting', async () => {
    watch();

    await elapse(5000);

    expect(kit.resume).not.toHaveBeenCalled();
    expect(kit.toast.warning).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('denies an approval that is already overdue, says so and takes it off the queue', async () => {
    const overdue = approvalRequest({ expiresAt: secondsFromNow(-1) });

    watch(overdue);
    await elapse(0);

    expect(kit.toast.warning).toHaveBeenCalledWith('timeoutAutoDenied');
    expect(kit.resume).toHaveBeenCalledTimes(1);
    expect(kit.resume.mock.calls[0][0]).toEqual(overdue);
    expect(decisions()).toEqual([
      expect.objectContaining({ type: 'reject', feedback: 'Auto-denied due to approval timeout' }),
    ]);
    expect(queueIds()).toEqual([]);
  });

  it('approves an overdue approval whose timeout behavior is allow', async () => {
    watch(approvalRequest({ expiresAt: secondsFromNow(-1), timeoutBehavior: 'allow' }));
    await elapse(0);

    expect(kit.toast.warning).toHaveBeenCalledWith('timeoutAutoApproved');
    expect(decisions()).toEqual([
      expect.objectContaining({ type: 'approve', feedback: 'Auto-approved due to approval timeout' }),
    ]);
  });

  it('answers at the very second the approval runs out, not a second later', async () => {
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
    watch(approvalRequest({ expiresAt: secondsFromNow(3) }));

    await elapse(2999);
    expect(kit.resume).not.toHaveBeenCalled();

    await elapse(1);
    expect(kit.resume).toHaveBeenCalledTimes(1);
  });

  it('waits for the approval to run out, then answers it exactly once', async () => {
    watch(approvalRequest({ expiresAt: secondsFromNow(3) }));

    await elapse(2000);
    expect(kit.resume).not.toHaveBeenCalled();

    await elapse(2000);
    expect(kit.resume).toHaveBeenCalledTimes(1);

    await elapse(10_000);
    expect(kit.resume).toHaveBeenCalledTimes(1);
    expect(kit.toast.warning).toHaveBeenCalledTimes(1);
  });

  it('answers only the approvals that ran out', async () => {
    watch(
      approvalRequest({ requestId: 'late', expiresAt: secondsFromNow(60) }),
      approvalRequest({ requestId: 'over', expiresAt: secondsFromNow(-1), messageId: 'msg-2' }),
    );
    await elapse(0);

    expect(kit.resume).toHaveBeenCalledTimes(1);
    expect(kit.resume.mock.calls[0][0]).toMatchObject({ requestId: 'over' });
    expect(queueIds()).toEqual(['late']);
  });

  it('does not answer an approval again when the queue changes around it', async () => {
    kit.resume.mockRejectedValue(new Error('offline'));
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    watch(approvalRequest({ requestId: 'over', expiresAt: secondsFromNow(-1) }));
    await elapse(0);
    expect(kit.resume).toHaveBeenCalledTimes(1);

    act(() => {
      useToolApprovalStore.setState((state) => ({
        queue: [...state.queue, approvalRequest({ requestId: 'new', messageId: 'msg-2' })],
      }));
    });
    await elapse(3000);

    expect(kit.resume).toHaveBeenCalledTimes(1);
  });

  it('claims nothing when the answer did not go through, the card stays and the failure is reported', async () => {
    kit.resume.mockRejectedValue(new Error('offline'));
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    watch(approvalRequest({ expiresAt: secondsFromNow(-1) }));
    await elapse(0);

    expect(kit.toast.warning).not.toHaveBeenCalled();
    expect(kit.toast.error).toHaveBeenCalledWith('resumeError');
    expect(queueIds()).toEqual(['req-1']);
  });

  it('stops checking once it is removed', async () => {
    const { unmount } = watch(approvalRequest({ expiresAt: secondsFromNow(3) }));
    unmount();

    await elapse(10_000);

    expect(kit.resume).not.toHaveBeenCalled();
  });

  it('answers a batch whose members all ran out together with one resume, in batch order, and says so once', async () => {
    const past = secondsFromNow(-1);
    watch(
      approvalRequest({ requestId: 'b2', batchId: 'batch', batchIndex: 1, expiresAt: past, timeoutBehavior: 'allow' }),
      approvalRequest({ requestId: 'b1', batchId: 'batch', batchIndex: 0, expiresAt: past, timeoutBehavior: 'allow' }),
    );
    await elapse(0);

    expect(kit.resume).toHaveBeenCalledTimes(1);
    expect(kit.resume.mock.calls[0][0]).toMatchObject({ requestId: 'b1' });
    expect(decisions().map((decision) => decision.type)).toEqual(['approve', 'approve']);
    expect(queueIds()).toEqual([]);
    expect(kit.toast.warning).toHaveBeenCalledTimes(1);
    expect(kit.toast.warning).toHaveBeenCalledWith('timeoutAutoApproved');
  });

  it('keeps the decision of a batch member that ran out until the rest of the batch is answered', async () => {
    watch(
      approvalRequest({ requestId: 'b1', batchId: 'batch', batchIndex: 0, expiresAt: secondsFromNow(-1) }),
      approvalRequest({ requestId: 'b2', batchId: 'batch', batchIndex: 1, expiresAt: secondsFromNow(30) }),
    );
    await elapse(0);

    expect(kit.resume).not.toHaveBeenCalled();
    expect(kit.toast.warning).not.toHaveBeenCalled();
    expect(queueIds()).toEqual(['b1', 'b2']);

    await elapse(31_000);

    expect(kit.resume).toHaveBeenCalledTimes(1);
    expect(decisions().map((decision) => decision.type)).toEqual(['reject', 'reject']);
    expect(queueIds()).toEqual([]);
    expect(kit.toast.warning).toHaveBeenCalledTimes(1);
  });

  it('says so for every batch and every single approval that ran out', async () => {
    const past = secondsFromNow(-1);
    watch(
      approvalRequest({ requestId: 'a1', batchId: 'a', batchIndex: 0, expiresAt: past }),
      approvalRequest({ requestId: 'a2', batchId: 'a', batchIndex: 1, expiresAt: past }),
      approvalRequest({ requestId: 'b1', batchId: 'b', batchIndex: 0, expiresAt: past, messageId: 'msg-b' }),
      approvalRequest({ requestId: 'b2', batchId: 'b', batchIndex: 1, expiresAt: past, messageId: 'msg-b' }),
      approvalRequest({ requestId: 'solo', expiresAt: past, messageId: 'msg-c' }),
    );
    await elapse(0);

    expect(kit.resume).toHaveBeenCalledTimes(3);
    expect(kit.toast.warning).toHaveBeenCalledTimes(3);
    expect(queueIds()).toEqual([]);
  });
});
