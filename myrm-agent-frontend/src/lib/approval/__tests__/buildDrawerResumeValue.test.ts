import { describe, expect, it } from 'vitest';

import { buildDrawerResumeValue, shouldResumeDrawerApproval } from '@/lib/approval/buildDrawerResumeValue';
import type { ResumeDecisionsPayload } from '@/lib/approval/approvalDecision';
import type { ApprovalPayload } from '@/store/useApprovalStore';

function decisionsOf(value: ReturnType<typeof buildDrawerResumeValue>): ResumeDecisionsPayload['decisions'] {
  return 'decisions' in value ? value.decisions : [];
}

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
    const decisions = decisionsOf(resumeValue);
    expect(decisions).toHaveLength(2);
    expect(decisions[0]).toMatchObject({
      type: 'approve',
      extensions: { allowAlways: false },
    });
  });

  it('forwards allow_always to every batch decision', () => {
    const resumeValue = buildDrawerResumeValue(baseApproval, 'approve', {
      allow_always: { tool: true },
      feedback: 'ok',
    });

    const decisions = decisionsOf(resumeValue);
    expect(decisions).toHaveLength(2);
    for (const decision of decisions) {
      expect(decision.extensions.allowAlways).toEqual({ tool: true });
      expect(decision.feedback).toBe('ok');
    }
  });

  it('forwards action_digest to approval decision when present in extra', () => {
    const digest = 'test_spend_action_digest_xyz123';
    const resumeValue = buildDrawerResumeValue(baseApproval, 'approve', {
      action_digest: digest,
      feedback: 'Approved spend',
    });

    const decisions = decisionsOf(resumeValue);
    expect(decisions).toHaveLength(2);
    for (const decision of decisions) {
      expect(decision.action_digest).toBe(digest);
      expect(decision.actionDigest).toBe(digest);
      expect(decision.extensions.action_digest).toBe(digest);
      expect(decision.extensions.actionDigest).toBe(digest);
    }
  });

  it('builds reject decisions with feedback', () => {
    const resumeValue = buildDrawerResumeValue(baseApproval, 'reject', { feedback: 'no' });
    const decisions = decisionsOf(resumeValue);
    expect(decisions[0]).toMatchObject({
      type: 'reject',
      feedback: 'no',
    });
  });

  it('carries the note written on an approval as guidance, not feedback', () => {
    // The harness reads `guidance` on an approval and `feedback` on a rejection; a note sent as
    // feedback on an approval is read by nobody.
    const resumeValue = buildDrawerResumeValue(baseApproval, 'approve', { guidance: 'only staging, not prod' });
    const decisions = decisionsOf(resumeValue);
    expect(decisions).toHaveLength(2);
    for (const decision of decisions) {
      expect(decision.guidance).toBe('only staging, not prod');
      expect(decision.feedback).toBeUndefined();
    }
  });

  it('carries the note written on a single-decision gate approval', () => {
    const domApproval: ApprovalPayload = {
      approval_id: 'dom-1',
      user_id: 'user-1',
      action_type: 'high_risk_dom_action',
      status: 'PENDING',
      severity: 'critical',
      chat_id: 'chat-1',
      payload: { tool_input: { action: 'evaluate', expression: 'document.forms[0].submit()' } },
    };

    expect(buildDrawerResumeValue(domApproval, 'approve', { guidance: 'use the staging URL' })).toEqual({
      decision: 'approve',
      guidance: 'use the staging URL',
    });
    // A plain approve stays exactly what it was.
    expect(buildDrawerResumeValue(domApproval, 'approve')).toEqual({ decision: 'approve' });
  });

  it('marks high_risk_dom_action as resumable with semantic decision payload', () => {
    expect(shouldResumeDrawerApproval('high_risk_dom_action')).toBe(true);

    const domApproval: ApprovalPayload = {
      approval_id: 'dom-1',
      user_id: 'user-1',
      action_type: 'high_risk_dom_action',
      status: 'PENDING',
      severity: 'critical',
      chat_id: 'chat-1',
      payload: {
        tool_input: { action: 'evaluate', expression: 'document.forms[0].submit()' },
      },
    };

    const approved = buildDrawerResumeValue(domApproval, 'approve');
    expect(approved).toEqual({ decision: 'approve' });

    const rejected = buildDrawerResumeValue(domApproval, 'reject', { feedback: 'too risky' });
    expect(rejected).toEqual({ decision: 'reject', feedback: 'too risky' });
  });

  it('resumes the batch cost gate so its decision reaches the delegation pause', () => {
    expect(shouldResumeDrawerApproval('batch_cost_approval')).toBe(true);

    const costApproval: ApprovalPayload = {
      approval_id: 'cost-1',
      user_id: 'user-1',
      action_type: 'batch_cost_approval',
      status: 'PENDING',
      severity: 'warning',
      chat_id: 'chat-1',
      payload: {
        task_count: 3,
        estimated_cost_usd: 4.43,
      },
    };

    expect(buildDrawerResumeValue(costApproval, 'approve')).toEqual({ decision: 'approve' });
    expect(buildDrawerResumeValue(costApproval, 'reject', { feedback: 'too expensive' })).toEqual({
      decision: 'reject',
      feedback: 'too expensive',
    });
  });

  it('resumes the privileged script gate so its decision reaches the browser pause', () => {
    expect(shouldResumeDrawerApproval('script_privileged_api')).toBe(true);

    const scriptApproval: ApprovalPayload = {
      approval_id: 'script-1',
      user_id: 'user-1',
      action_type: 'script_privileged_api',
      status: 'PENDING',
      severity: 'warning',
      chat_id: 'chat-1',
      payload: {
        tool_name: 'browser_execute_script_tool',
        reason: 'Script accesses privileged APIs that bypass network policy: .request.get()',
      },
    };

    expect(buildDrawerResumeValue(scriptApproval, 'approve')).toEqual({ decision: 'approve' });
    expect(buildDrawerResumeValue(scriptApproval, 'reject')).toEqual({
      decision: 'reject',
      feedback: 'User rejected this action.',
    });
  });

  it('builds edit decision with edited args for single-tool batch', () => {    const singleToolApproval: ApprovalPayload = {
      ...baseApproval,
      payload: {
        tool_calls: [{ name: 'bash_code_execute_tool', args: { command: 'ls' } }],
      },
    };
    const resumeValue = buildDrawerResumeValue(singleToolApproval, 'edit', {
      edited_args: { command: 'pwd' },
      allow_always: { tool: true },
    });
    const decisions = decisionsOf(resumeValue);
    expect(decisions).toHaveLength(1);
    expect(decisions[0]).toMatchObject({
      type: 'edit',
      args: { command: 'pwd' },
      extensions: { allowAlways: { tool: true } },
    });
  });
});
