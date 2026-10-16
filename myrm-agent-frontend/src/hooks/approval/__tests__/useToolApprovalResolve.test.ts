import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import { ApprovalExpiredError, RiskBlockedError } from '@/store/chat/streamErrors';
import type { ToolApprovalRequest } from '@/store/chat/types';
import useToolApprovalStore from '@/store/useToolApprovalStore';

const mockResumeApprovalStream = vi.hoisted(() => vi.fn());
const toastError = vi.hoisted(() => vi.fn());
const toastWarning = vi.hoisted(() => vi.fn());

vi.mock('@/lib/approval/resumeApprovalStream', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/approval/resumeApprovalStream')>()),
  resumeApprovalStream: (...args: unknown[]) => mockResumeApprovalStream(...args),
}));

vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
    warning: (...args: unknown[]) => toastWarning(...args),
    info: vi.fn(),
  },
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

import { useToolApprovalResolve } from '../useToolApprovalResolve';

function buildRequest(): ToolApprovalRequest {
  return {
    requestId: 'req-1',
    toolName: 'bash',
    toolInput: {},
    reason: 'test',
    timeoutSeconds: 300,
    expiresAt: Math.floor(Date.now() / 1000) + 300,
    timeoutBehavior: 'deny',
    messageId: 'msg-1',
    displayMode: 'approval',
    chatId: 'chat-1',
    actionMode: 'agent',
  };
}

describe('useToolApprovalResolve: a typed rejection reason', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useToolApprovalStore.setState({ queue: [buildRequest()], batchDecisions: new Map(), isResolving: false });
  });

  async function reject() {
    const { result } = renderHook(() => useToolApprovalResolve());
    await act(async () => {
      await result.current.resolveRequest('req-1', 'reject', { feedback: 'use the key' });
    });
  }

  it('leaves the approval pending and adds no failure notice when a risk rule holds it', async () => {
    mockResumeApprovalStream.mockRejectedValue(new RiskBlockedError());

    await reject();

    expect(useToolApprovalStore.getState().queue.map((r) => r.requestId)).toEqual(['req-1']);
    expect(toastError).not.toHaveBeenCalled();
    expect(useToolApprovalStore.getState().isResolving).toBe(false);
  });

  it('still reports any other failed resume and keeps the approval pending', async () => {
    mockResumeApprovalStream.mockRejectedValue(new Error('boom'));

    await reject();

    expect(useToolApprovalStore.getState().queue.map((r) => r.requestId)).toEqual(['req-1']);
    expect(toastError).toHaveBeenCalledWith('resumeError');
  });

  it('closes the approval once the server took the reason', async () => {
    mockResumeApprovalStream.mockResolvedValue(undefined);

    await reject();

    expect(useToolApprovalStore.getState().queue).toEqual([]);
    expect(toastError).not.toHaveBeenCalled();
  });

  it('collapses the approval with a warning when the timeout already answered it', async () => {
    mockResumeApprovalStream.mockRejectedValue(new ApprovalExpiredError());

    await reject();

    expect(useToolApprovalStore.getState().queue).toEqual([]);
    expect(toastWarning).toHaveBeenCalledWith('approvalExpired');
  });
});
