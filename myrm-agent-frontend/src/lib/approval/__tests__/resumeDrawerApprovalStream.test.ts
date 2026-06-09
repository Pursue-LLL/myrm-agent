import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { ApprovalPayload } from '@/store/useApprovalStore';

const resumeApprovalStreamMock = vi.fn().mockResolvedValue(undefined);

vi.mock('@/lib/approval/resumeApprovalStream', () => ({
  resumeApprovalStream: resumeApprovalStreamMock,
}));

describe('resumeDrawerApprovalStream', () => {
  beforeEach(() => {
    resumeApprovalStreamMock.mockClear();
  });

  it('forwards allow_always into resume decisions', async () => {
    const { resumeDrawerApprovalStream } = await import('@/lib/approval/resumeDrawerApprovalStream');

    const approval: ApprovalPayload = {
      approval_id: 'approval-1',
      user_id: 'user-1',
      action_type: 'subagent_approval',
      status: 'PENDING',
      severity: 'warning',
      chat_id: 'chat-1',
      payload: {
        tool_calls: [{ name: 'bash_code_execute_tool', args: { command: 'echo hi' } }],
      },
    };

    await resumeDrawerApprovalStream(
      approval,
      'approve',
      { allow_always: { tool: true }, feedback: 'ok' },
      'resume failed',
    );

    expect(resumeApprovalStreamMock).toHaveBeenCalledTimes(1);
    const resumeValue = resumeApprovalStreamMock.mock.calls[0]?.[1] as {
      decisions: Array<{ extensions: { allowAlways: { tool: boolean } } }>;
    };
    expect(resumeValue.decisions[0]?.extensions.allowAlways).toEqual({ tool: true });
  });

  it('skips resume when chat_id is missing', async () => {
    const { resumeDrawerApprovalStream } = await import('@/lib/approval/resumeDrawerApprovalStream');

    await resumeDrawerApprovalStream(
      {
        approval_id: 'approval-2',
        user_id: 'user-1',
        action_type: 'subagent_approval',
        status: 'PENDING',
        severity: 'warning',
        payload: {},
      },
      'approve',
      undefined,
      'resume failed',
    );

    expect(resumeApprovalStreamMock).not.toHaveBeenCalled();
  });
});
