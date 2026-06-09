import { describe, expect, it } from 'vitest';

import { buildDrawerResumeValue, shouldResumeDrawerApproval } from '@/lib/approval/buildDrawerResumeValue';
import type { ApprovalPayload } from '@/store/useApprovalStore';

const baseApproval: ApprovalPayload = {
  approval_id: 'approval-1',
  user_id: 'user-1',
  action_type: 'subagent_approval',
  status: 'PENDING',
  severity: 'warning',
  chat_id: 'chat-1',
  payload: {
    tool_calls: [
      { name: 'bash_code_execute_tool', args: { command: 'echo hi' } },
      { name: 'bash_code_execute_tool', args: { command: 'pwd' } },
    ],
  },
};

describe('buildDrawerResumeValue', () => {
  it('marks subagent approvals as resumable', () => {
    expect(shouldResumeDrawerApproval('subagent_approval')).toBe(true);
    expect(shouldResumeDrawerApproval('skill_draft')).toBe(false);
  });

  it('builds one decision per subagent tool call', () => {
    const resumeValue = buildDrawerResumeValue(baseApproval, 'approve');
    expect(resumeValue.decisions).toHaveLength(2);
    expect(resumeValue.decisions[0]).toMatchObject({
      type: 'approve',
      extensions: { allowAlways: false },
    });
  });

  it('forwards allow_always to every batch decision', () => {
    const resumeValue = buildDrawerResumeValue(baseApproval, 'approve', {
      allow_always: { tool: true },
      feedback: 'ok',
    });

    expect(resumeValue.decisions).toHaveLength(2);
    for (const decision of resumeValue.decisions) {
      expect(decision.extensions.allowAlways).toEqual({ tool: true });
      expect(decision.feedback).toBe('ok');
    }
  });

  it('builds reject decisions with feedback', () => {
    const resumeValue = buildDrawerResumeValue(baseApproval, 'reject', { feedback: 'no' });
    expect(resumeValue.decisions[0]).toMatchObject({
      type: 'reject',
      feedback: 'no',
    });
  });

  it('builds edit decision with edited args for single-tool batch', () => {
    const singleToolApproval: ApprovalPayload = {
      ...baseApproval,
      payload: {
        tool_calls: [{ name: 'bash_code_execute_tool', args: { command: 'ls' } }],
      },
    };
    const resumeValue = buildDrawerResumeValue(singleToolApproval, 'edit', {
      edited_args: { command: 'pwd' },
      allow_always: { tool: true },
    });
    expect(resumeValue.decisions).toHaveLength(1);
    expect(resumeValue.decisions[0]).toMatchObject({
      type: 'edit',
      args: { command: 'pwd' },
      extensions: { allowAlways: { tool: true } },
    });
  });
});
