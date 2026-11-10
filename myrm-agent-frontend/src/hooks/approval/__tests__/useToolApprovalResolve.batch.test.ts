import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApprovalAlreadyResolvedError } from '@/store/chat/streamErrors';
import type { ToolApprovalRequest } from '@/store/chat/types';
import useToolApprovalStore from '@/store/useToolApprovalStore';

const hoisted = vi.hoisted(() => ({ resume: vi.fn(), info: vi.fn(), warning: vi.fn(), error: vi.fn() }));

vi.mock('@/lib/approval/resumeApprovalStream', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/approval/resumeApprovalStream')>()),
  resumeApprovalStream: (...args: unknown[]) => hoisted.resume(...args),
}));
vi.mock('sonner', () => ({ toast: { info: hoisted.info, warning: hoisted.warning, error: hoisted.error } }));

const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));

import { useToolApprovalResolve } from '../useToolApprovalResolve';

function request(requestId: string, batchId?: string, batchIndex?: number): ToolApprovalRequest {
  return {
    requestId,
    toolName: 'bash_code_execute_tool',
    toolInput: {},
    reason: '',
    timeoutSeconds: 300,
    expiresAt: Math.floor(Date.now() / 1000) + 300,
    timeoutBehavior: 'deny',
    messageId: `msg-${batchId ?? requestId}`,
    displayMode: 'approval',
    chatId: 'chat-1',
    actionMode: 'agent',
    batchId,
    batchIndex,
  };
}

const queueIds = () => useToolApprovalStore.getState().queue.map((r) => r.requestId);
const decidedIds = () => [...useToolApprovalStore.getState().batchDecisions.keys()];
const resumedWith = (call: number) => {
  const decisions = (hoisted.resume.mock.calls[call][1] as { decisions: Array<{ type: string; feedback?: string }> })
    .decisions;
  return {
    first: (hoisted.resume.mock.calls[call][0] as ToolApprovalRequest).requestId,
    types: decisions.map((decision) => decision.type),
    feedbacks: decisions.map((decision) => decision.feedback),
  };
};

function setup(...queue: ToolApprovalRequest[]) {
  useToolApprovalStore.setState({ queue, batchDecisions: new Map(), isResolving: false });
  return renderHook(() => useToolApprovalResolve());
}

beforeEach(() => {
  vi.resetAllMocks();
  hoisted.resume.mockResolvedValue(undefined);
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

describe('useToolApprovalResolve: answering a batch member by member', () => {
  it('waits and says how many are decided until the last member answers, then sends all in batch order', async () => {
    const { result } = setup(request('b2', 'x', 1), request('b1', 'x', 0));

    await act(() => result.current.resolveRequest('b2', 'approve'));
    expect(hoisted.info).toHaveBeenCalledWith('batchPending:{"decided":1,"total":2}');
    expect(hoisted.resume).not.toHaveBeenCalled();
    expect(queueIds()).toEqual(['b2', 'b1']);

    await act(() => result.current.resolveRequest('b1', 'reject', { feedback: 'no' }));

    expect(hoisted.resume).toHaveBeenCalledTimes(1);
    expect(resumedWith(0)).toEqual({ first: 'b1', types: ['reject', 'approve'], feedbacks: ['no', undefined] });
    expect(queueIds()).toEqual([]);
    expect(decidedIds()).toEqual([]);
  });

  it('lets answers given in the same tick see each other', async () => {
    const { result } = setup(request('b1', 'x', 0), request('b2', 'x', 1));

    await act(async () => {
      await Promise.all([result.current.resolveRequest('b2', 'reject'), result.current.resolveRequest('b1', 'reject')]);
    });

    expect(hoisted.resume).toHaveBeenCalledTimes(1);
    expect(resumedWith(0)).toEqual({ first: 'b1', types: ['reject', 'reject'], feedbacks: [undefined, undefined] });
    expect(queueIds()).toEqual([]);
  });

  it('counts only the decisions of the batch being answered', async () => {
    const { result } = setup(
      request('x1', 'x', 0),
      request('x2', 'x', 1),
      request('y1', 'y', 0),
      request('y2', 'y', 1),
    );

    await act(() => result.current.resolveRequest('x1', 'approve'));
    await act(() => result.current.resolveRequest('y1', 'approve'));

    expect(hoisted.info).toHaveBeenLastCalledWith('batchPending:{"decided":1,"total":2}');
  });

  it('keeps the decisions of a batch that is still open when another batch is sent', async () => {
    const { result } = setup(
      request('x1', 'x', 0),
      request('x2', 'x', 1),
      request('y1', 'y', 0),
      request('y2', 'y', 1),
    );

    await act(() => result.current.resolveRequest('x1', 'reject'));
    await act(() => result.current.resolveRequest('y1', 'approve'));
    await act(() => result.current.resolveRequest('y2', 'approve'));
    expect(resumedWith(0)).toEqual({ first: 'y1', types: ['approve', 'approve'], feedbacks: [undefined, undefined] });
    expect(queueIds()).toEqual(['x1', 'x2']);

    await act(() => result.current.resolveRequest('x2', 'approve'));

    expect(hoisted.resume).toHaveBeenCalledTimes(2);
    expect(resumedWith(1)).toEqual({ first: 'x1', types: ['reject', 'approve'], feedbacks: [undefined, undefined] });
    expect(queueIds()).toEqual([]);
  });

  it('keeps the decisions of an open batch when everything shown is approved at once', async () => {
    const { result } = setup(request('x1', 'x', 0), request('x2', 'x', 1), request('solo'));

    await act(() => result.current.resolveRequest('x1', 'reject'));
    await act(() => result.current.approveAll([request('solo')]));

    expect(queueIds()).toEqual(['x1', 'x2']);
    expect(decidedIds()).toEqual(['x1']);
  });

  it('forgets the decisions of the requests it answered in bulk', async () => {
    const { result } = setup(request('x1', 'x', 0), request('x2', 'x', 1), request('solo'));

    await act(() => result.current.resolveRequest('x1', 'reject'));
    await act(() => result.current.approveAll([request('x1', 'x', 0), request('x2', 'x', 1)]));

    expect(decidedIds()).toEqual([]);
    expect(queueIds()).toEqual(['solo']);
  });

  it('does nothing for an empty selection', async () => {
    const { result } = setup(request('solo'));
    const busy: boolean[] = [];
    const unsubscribe = useToolApprovalStore.subscribe((state) => busy.push(state.isResolving));

    await act(() => result.current.approveAll([]));
    unsubscribe();

    expect(hoisted.resume).not.toHaveBeenCalled();
    expect(busy).not.toContain(true);
  });

  it('asks for every decision again after the batch could not be sent', async () => {
    hoisted.resume.mockRejectedValueOnce(new Error('offline'));
    const { result } = setup(request('b1', 'x', 0), request('b2', 'x', 1));

    await act(() => result.current.resolveRequest('b1', 'approve'));
    await act(() => result.current.resolveRequest('b2', 'approve'));
    expect(hoisted.error).toHaveBeenCalledWith('resumeError');
    expect(queueIds()).toEqual(['b1', 'b2']);
    expect(decidedIds()).toEqual([]);

    await act(() => result.current.resolveRequest('b1', 'reject'));
    await act(() => result.current.resolveRequest('b2', 'reject'));

    expect(hoisted.resume).toHaveBeenCalledTimes(2);
    expect(resumedWith(1)).toEqual({ first: 'b1', types: ['reject', 'reject'], feedbacks: [undefined, undefined] });
    expect(queueIds()).toEqual([]);
  });

  it('removes the whole batch when the server had already resolved it', async () => {
    hoisted.resume.mockRejectedValue(new ApprovalAlreadyResolvedError());
    const { result } = setup(request('b1', 'x', 0), request('b2', 'x', 1), request('other'));

    await act(() => result.current.resolveRequest('b1', 'approve'));
    await act(() => result.current.resolveRequest('b2', 'approve'));

    expect(hoisted.warning).toHaveBeenCalledWith('approvalAlreadyHandled');
    expect(queueIds()).toEqual(['other']);
  });

  it('ignores an answer for an approval that is no longer waiting', async () => {
    const { result } = setup(request('b1', 'x', 0));

    await act(() => result.current.resolveRequest('gone', 'approve'));

    expect(hoisted.resume).not.toHaveBeenCalled();
    expect(hoisted.info).not.toHaveBeenCalled();
    expect(hoisted.error).not.toHaveBeenCalled();
    expect(decidedIds()).toEqual([]);
    expect(useToolApprovalStore.getState().isResolving).toBe(false);
  });
});

describe('useToolApprovalResolve: answering several interrupts at once', () => {
  const interrupts = () => [request('a'), request('b'), request('c')];

  it('sends approvals without a reason and rejections with one the agent can read', async () => {
    const { result } = setup(...interrupts(), request('d'));

    await act(() => result.current.approveAll(interrupts()));
    await act(() => result.current.rejectAll([request('d')]));

    expect(hoisted.resume).toHaveBeenCalledTimes(4);
    expect([0, 1, 2].map((call) => resumedWith(call).feedbacks)).toEqual([[undefined], [undefined], [undefined]]);
    expect(resumedWith(3)).toEqual({ first: 'd', types: ['reject'], feedbacks: ['Batch rejected by user'] });
    expect(hoisted.warning).not.toHaveBeenCalled();
    expect(queueIds()).toEqual([]);
  });

  it('keeps answering the other interrupts when one was already answered elsewhere, and says so once', async () => {
    hoisted.resume.mockRejectedValueOnce(new ApprovalAlreadyResolvedError());
    const { result } = setup(...interrupts());

    await act(() => result.current.approveAll(interrupts()));

    expect(hoisted.resume).toHaveBeenCalledTimes(3);
    expect(hoisted.warning).toHaveBeenCalledTimes(1);
    expect(hoisted.warning).toHaveBeenCalledWith('approvalAlreadyHandled');
    expect(hoisted.error).not.toHaveBeenCalled();
    expect(queueIds()).toEqual([]);
  });

  it('says so once however many interrupts were answered elsewhere', async () => {
    hoisted.resume.mockRejectedValue(new ApprovalAlreadyResolvedError());
    const { result } = setup(...interrupts());

    await act(() => result.current.rejectAll(interrupts()));

    expect(hoisted.resume).toHaveBeenCalledTimes(3);
    expect(hoisted.warning).toHaveBeenCalledTimes(1);
    expect(queueIds()).toEqual([]);
  });

  it('stops at the first interrupt it cannot send and keeps that one and the rest to answer again', async () => {
    hoisted.resume.mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error('offline'));
    const { result } = setup(...interrupts());

    await act(() => result.current.approveAll(interrupts()));

    expect(hoisted.resume).toHaveBeenCalledTimes(2);
    expect(hoisted.error).toHaveBeenCalledWith('resumeError');
    expect(hoisted.warning).not.toHaveBeenCalled();
    expect(queueIds()).toEqual(['b', 'c']);
    expect(useToolApprovalStore.getState().isResolving).toBe(false);
  });
});
